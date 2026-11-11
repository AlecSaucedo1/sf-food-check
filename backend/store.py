from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .normalize import normalize_row
from .taxonomy import extract_source_violations

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS inspections (
    inspection_id TEXT PRIMARY KEY,
    permit_number TEXT NOT NULL,
    dba TEXT NOT NULL,
    street_address TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    analysis_neighborhood TEXT,
    supervisor_district TEXT,
    inspection_date TEXT,
    inspection_type TEXT,
    inspection_frequency_type TEXT,
    inspector TEXT,
    permit_type TEXT,
    total_time_minutes INTEGER,
    facility_rating_status TEXT,
    violation_count INTEGER DEFAULT 0,
    violation_codes_json TEXT NOT NULL DEFAULT '[]',
    latitude REAL,
    longitude REAL,
    data_as_of TEXT,
    raw_row_id TEXT,
    source_notes TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inspections_permit ON inspections(permit_number);
CREATE INDEX IF NOT EXISTS idx_inspections_date ON inspections(inspection_date DESC);
CREATE INDEX IF NOT EXISTS idx_inspections_name ON inspections(dba COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(facility_rating_status);
CREATE INDEX IF NOT EXISTS idx_inspections_permit_date ON inspections(permit_number, inspection_date DESC, inspection_id DESC);

-- One record per facility. Rebuilt transactionally during ingestion, rather than
-- recalculating a 65,000-row window function on every search request.
CREATE TABLE IF NOT EXISTS facility_latest (
    permit_number TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL,
    dba TEXT NOT NULL,
    street_address TEXT,
    analysis_neighborhood TEXT,
    facility_rating_status TEXT,
    inspection_date TEXT,
    violation_count INTEGER,
    latitude REAL,
    longitude REAL
);
CREATE INDEX IF NOT EXISTS idx_facility_latest_date ON facility_latest(inspection_date DESC);
CREATE INDEX IF NOT EXISTS idx_facility_latest_status ON facility_latest(facility_rating_status);
CREATE INDEX IF NOT EXISTS idx_facility_latest_neighborhood ON facility_latest(analysis_neighborhood);
CREATE INDEX IF NOT EXISTS idx_facility_latest_geo ON facility_latest(latitude, longitude);

CREATE TABLE IF NOT EXISTS report_enrichment (
    permit_number TEXT NOT NULL,
    inspection_date TEXT NOT NULL,
    report_url TEXT,
    inspector_comments TEXT,
    corrective_action TEXT,
    comment_source TEXT NOT NULL DEFAULT 'manual_official',
    source_label TEXT,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(permit_number, inspection_date)
);

CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id TEXT NOT NULL,
    code TEXT,
    official_description TEXT,
    normalized_category TEXT,
    consumer_description TEXT,
    risk_level TEXT,
    inspector_comment TEXT,
    FOREIGN KEY(inspection_id) REFERENCES inspections(inspection_id)
);
CREATE INDEX IF NOT EXISTS idx_violations_inspection ON violations(inspection_id);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    facility_count INTEGER NOT NULL DEFAULT 0,
    latest_inspection_date TEXT,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sync_runs_completed ON sync_runs(completed_at DESC);
"""


# Schema initialization is keyed to the actual SQLite file inode, not the
# symlink path: an atomic deployment swap gets its own initialization.
_SCHEMA_READY: set[tuple[int, int]] = set()
_SCHEMA_LOCK = threading.Lock()


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    try:
        stat = os.stat(db_path)
        identity = (stat.st_dev, stat.st_ino)
        if identity not in _SCHEMA_READY:
            with _SCHEMA_LOCK:
                if identity not in _SCHEMA_READY:
                    con.executescript(SCHEMA)
                    _SCHEMA_READY.add(identity)
        return con
    except Exception:
        con.close()
        raise


def refresh_facility_latest(con: sqlite3.Connection) -> None:
    """Rebuild the read-optimized facility index inside the active transaction."""
    con.execute("DELETE FROM facility_latest")
    con.execute("""
        INSERT INTO facility_latest (
          permit_number, inspection_id, dba, street_address, analysis_neighborhood,
          facility_rating_status, inspection_date, violation_count, latitude, longitude
        )
        SELECT permit_number, inspection_id, dba, street_address, analysis_neighborhood,
               facility_rating_status, inspection_date, violation_count, latitude, longitude
        FROM (
          SELECT permit_number, inspection_id, dba, street_address, analysis_neighborhood,
                 facility_rating_status, inspection_date, violation_count, latitude, longitude,
                 ROW_NUMBER() OVER (
                   PARTITION BY permit_number
                   ORDER BY inspection_date DESC, inspection_id DESC
                 ) AS row_number
          FROM inspections
        )
        WHERE row_number = 1
    """)


def _ensure_facility_latest(con: sqlite3.Connection) -> None:
    # Handles older local databases and import paths that do not yet maintain
    # the derived index. Production bundles already populate it at build time.
    if con.execute("SELECT 1 FROM facility_latest LIMIT 1").fetchone() is None:
        if con.execute("SELECT 1 FROM inspections LIMIT 1").fetchone() is not None:
            refresh_facility_latest(con)
            con.commit()


def _blank(value: Any) -> bool:
    return value in (None, "", [], {})


def _status_rank(value: str) -> int:
    return {"Unknown": 0, "Pass": 1, "Conditional Pass": 2, "Closure": 3}.get(value or "Unknown", 0)


def _combine_text(a: Any, b: Any, separator: str = " | ") -> str:
    left, right = str(a or "").strip(), str(b or "").strip()
    if not left:
        return right
    if not right or right == left:
        return left
    pieces = [p.strip() for p in left.split(separator) if p.strip()]
    if right not in pieces:
        pieces.append(right)
    return separator.join(pieces)


def _merge_normalized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate DataSF rows that represent one inspection.

    DataSF can publish a summary row and one or more violation-bearing rows for the
    same permit/date/type. We merge those rows before writing SQLite so an empty
    summary row can never overwrite the actual findings.
    """
    merged: dict[str, dict[str, Any]] = {}
    cutoff = date.today() + timedelta(days=1)

    for raw in rows:
        incoming = normalize_row(raw)
        inspection_date = incoming.get("inspection_date")
        if inspection_date:
            try:
                # The dataset describes completed inspections. Ignore obviously
                # future-dated records (e.g. erroneous 2031 dates in a 2026 feed).
                if date.fromisoformat(inspection_date) > cutoff:
                    continue
            except ValueError:
                pass

        key = incoming["inspection_id"]
        if key not in merged:
            merged[key] = incoming
            continue

        current = merged[key]
        current["violation_count"] = max(int(current.get("violation_count") or 0), int(incoming.get("violation_count") or 0))
        current["total_time_minutes"] = max(int(current.get("total_time_minutes") or 0), int(incoming.get("total_time_minutes") or 0)) or None
        if _status_rank(incoming.get("facility_rating_status", "Unknown")) > _status_rank(current.get("facility_rating_status", "Unknown")):
            current["facility_rating_status"] = incoming["facility_rating_status"]

        combined_codes = list(current.get("violation_codes") or [])
        for value in incoming.get("violation_codes") or []:
            if value not in combined_codes:
                combined_codes.append(value)
        current["violation_codes"] = combined_codes
        current["source_notes"] = _combine_text(current.get("source_notes"), incoming.get("source_notes"))

        for field in (
            "dba", "street_address", "city", "state", "zip", "analysis_neighborhood",
            "supervisor_district", "inspection_frequency_type", "inspector", "permit_type",
            "latitude", "longitude", "data_as_of", "raw_row_id",
        ):
            if _blank(current.get(field)) and not _blank(incoming.get(field)):
                current[field] = incoming[field]

        current_raw = current.get("raw") if isinstance(current.get("raw"), dict) else {}
        incoming_raw = incoming.get("raw") if isinstance(incoming.get("raw"), dict) else {}
        for field, value in incoming_raw.items():
            if _blank(value):
                continue
            existing = current_raw.get(field)
            if _blank(existing):
                current_raw[field] = value
            elif existing != value and ("violation" in str(field).lower() or "note" in str(field).lower()):
                current_raw[field] = _combine_text(existing, value)
        current["raw"] = current_raw

    return list(merged.values())


def upsert_inspections(con: sqlite3.Connection, rows: list[dict[str, Any]], *, commit: bool = True) -> int:
    normalized = _merge_normalized_rows(rows)
    sql = """
    INSERT INTO inspections (
        inspection_id, permit_number, dba, street_address, city, state, zip,
        analysis_neighborhood, supervisor_district, inspection_date, inspection_type,
        inspection_frequency_type, inspector, permit_type, total_time_minutes,
        facility_rating_status, violation_count, violation_codes_json, latitude, longitude,
        data_as_of, raw_row_id, source_notes, raw_json
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(inspection_id) DO UPDATE SET
        permit_number=excluded.permit_number, dba=excluded.dba, street_address=excluded.street_address,
        city=excluded.city, state=excluded.state, zip=excluded.zip,
        analysis_neighborhood=excluded.analysis_neighborhood, supervisor_district=excluded.supervisor_district,
        inspection_date=excluded.inspection_date, inspection_type=excluded.inspection_type,
        inspection_frequency_type=excluded.inspection_frequency_type, inspector=excluded.inspector,
        permit_type=excluded.permit_type, total_time_minutes=excluded.total_time_minutes,
        facility_rating_status=excluded.facility_rating_status, violation_count=excluded.violation_count,
        violation_codes_json=excluded.violation_codes_json, latitude=excluded.latitude,
        longitude=excluded.longitude, data_as_of=excluded.data_as_of, raw_row_id=excluded.raw_row_id,
        source_notes=excluded.source_notes, raw_json=excluded.raw_json
    """
    for n in normalized:
        con.execute(sql, (
            n["inspection_id"], n["permit_number"], n["dba"], n["street_address"], n["city"], n["state"], n["zip"],
            n["analysis_neighborhood"], n["supervisor_district"], n["inspection_date"], n["inspection_type"],
            n["inspection_frequency_type"], n["inspector"], n["permit_type"], n["total_time_minutes"],
            n["facility_rating_status"], n["violation_count"], json.dumps(n["violation_codes"]), n["latitude"], n["longitude"],
            n["data_as_of"], n["raw_row_id"], n["source_notes"], json.dumps(n["raw"], ensure_ascii=False),
        ))
    if commit:
        refresh_facility_latest(con)
        con.commit()
    return len(normalized)


def replace_inspections(con: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM violations")
        con.execute("DELETE FROM inspections")
        count = upsert_inspections(con, rows, commit=False)
        refresh_facility_latest(con)
        con.commit()
        return count
    except Exception:
        con.rollback()
        raise


def record_sync_run(con: sqlite3.Connection, *, started_at: str, completed_at: str, success: bool, row_count: int, facility_count: int, latest_inspection_date: str | None, error: str) -> None:
    con.execute("""INSERT INTO sync_runs
        (started_at, completed_at, success, row_count, facility_count, latest_inspection_date, error)
        VALUES (?,?,?,?,?,?,?)""", (started_at, completed_at, 1 if success else 0, row_count, facility_count, latest_inspection_date, error))
    con.commit()


def latest_sync_run(con: sqlite3.Connection) -> dict[str, Any] | None:
    row = con.execute("""SELECT started_at, completed_at, success, row_count, facility_count, latest_inspection_date, error
        FROM sync_runs ORDER BY id DESC LIMIT 1""").fetchone()
    return dict(row) if row else None


def import_enrichment(con: sqlite3.Connection, items: list[dict[str, Any]]) -> int:
    for item in items:
        con.execute("""
            INSERT INTO report_enrichment
              (permit_number, inspection_date, report_url, inspector_comments, corrective_action, comment_source, source_label)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(permit_number, inspection_date) DO UPDATE SET
              report_url=excluded.report_url,
              inspector_comments=excluded.inspector_comments,
              corrective_action=excluded.corrective_action,
              comment_source=excluded.comment_source,
              source_label=excluded.source_label,
              imported_at=CURRENT_TIMESTAMP
            """, (
                str(item.get("permit_number", "")), str(item.get("inspection_date", "")), item.get("report_url"), item.get("inspector_comments"), item.get("corrective_action"), item.get("comment_source", "manual_official"), item.get("source_label"),
            ))
    con.commit()
    return len(items)


def seed_demo(con: sqlite3.Connection, path: str) -> None:
    count = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
    if count:
        return
    payload = json.loads(Path(path).read_text())
    upsert_inspections(con, payload["rows"])
    import_enrichment(con, payload.get("enrichment", []))
    for v in payload.get("violations", []):
        con.execute("""INSERT INTO violations
            (inspection_id, code, official_description, normalized_category, consumer_description, risk_level, inspector_comment)
            VALUES (?,?,?,?,?,?,?)""", (v["inspection_id"], v.get("code"), v.get("official_description"), v.get("normalized_category"), v.get("consumer_description"), v.get("risk_level"), v.get("inspector_comment")))
    con.commit()


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))


def _row_to_inspection(row: sqlite3.Row, con: sqlite3.Connection) -> dict[str, Any]:
    data = dict(row)
    data["violation_codes"] = json.loads(data.pop("violation_codes_json") or "[]")
    try:
        raw_source = json.loads(data.pop("raw_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raw_source = {}
    data["source_violations"] = extract_source_violations(raw_source, data["violation_codes"])
    data["source_violation_fields"] = sorted(str(k) for k in raw_source.keys() if "violation" in str(k).lower())

    enrich = con.execute("SELECT report_url, inspector_comments, corrective_action, comment_source, source_label FROM report_enrichment WHERE permit_number=? AND inspection_date=?", (data["permit_number"], data["inspection_date"])).fetchone()
    data["report"] = dict(enrich) if enrich else None
    violations = con.execute("SELECT code, official_description, normalized_category, consumer_description, risk_level, inspector_comment FROM violations WHERE inspection_id=?", (data["inspection_id"],)).fetchall()
    data["violations"] = [dict(v) for v in violations]
    return data


def _listing_rows(con: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Fetch compact five-item history only for the facilities returned."""
    output = []
    for row in rows:
        base = dict(row)
        history = con.execute(
            "SELECT facility_rating_status, inspection_date FROM inspections "
            "WHERE permit_number=? ORDER BY inspection_date DESC, inspection_id DESC LIMIT 5",
            (base["permit_number"],),
        ).fetchall()
        output.append({
            "permit_number": base["permit_number"],
            "dba": base["dba"],
            "street_address": base["street_address"],
            "analysis_neighborhood": base["analysis_neighborhood"],
            "facility_rating_status": base["facility_rating_status"],
            "inspection_date": base["inspection_date"],
            "violation_count": base["violation_count"],
            "latitude": base["latitude"],
            "longitude": base["longitude"],
            "history": [dict(h) for h in history],
        })
    return output


def list_restaurants(con: sqlite3.Connection, q: str = "", status: str = "", neighborhood: str = "", limit: int = 50) -> list[dict[str, Any]]:
    _ensure_facility_latest(con)
    where, params = [], []
    if q:
        where.append("(dba LIKE ? OR street_address LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if status:
        where.append("facility_rating_status = ?")
        params.append(status)
    if neighborhood:
        where.append("analysis_neighborhood = ?")
        params.append(neighborhood)
    clause = "WHERE " + " AND ".join(where) if where else ""
    rows = con.execute(
        f"SELECT * FROM facility_latest {clause} "
        "ORDER BY inspection_date DESC, dba COLLATE NOCASE LIMIT ?",
        (*params, max(1, min(limit, 200))),
    ).fetchall()
    return _listing_rows(con, rows)

def restaurant_detail(con: sqlite3.Connection, permit_number: str) -> dict[str, Any] | None:
    rows = con.execute("SELECT * FROM inspections WHERE permit_number=? ORDER BY inspection_date DESC, inspection_id DESC", (permit_number,)).fetchall()
    if not rows:
        return None
    inspections = [_row_to_inspection(r, con) for r in rows]
    latest = inspections[0]
    return {"permit_number": permit_number, "dba": latest["dba"], "street_address": latest["street_address"], "city": latest["city"], "state": latest["state"], "zip": latest["zip"], "analysis_neighborhood": latest["analysis_neighborhood"], "latitude": latest["latitude"], "longitude": latest["longitude"], "current_status": latest["facility_rating_status"], "latest_inspection_date": latest["inspection_date"], "inspections": inspections}


def nearby(con: sqlite3.Connection, lat: float, lon: float, radius_km: float = 2.0, limit: int = 50) -> list[dict[str, Any]]:
    """Search every geocoded facility in the bounding box, not just the latest 200."""
    _ensure_facility_latest(con)
    delta_lat = radius_km / 111.1
    cos_lat = max(0.01, abs(math.cos(math.radians(lat))))
    delta_lon = radius_km / (111.1 * cos_lat)
    rows = con.execute(
        "SELECT * FROM facility_latest WHERE latitude BETWEEN ? AND ? "
        "AND longitude BETWEEN ? AND ?",
        (lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon),
    ).fetchall()
    located = []
    for row in rows:
        distance = _distance_km(lat, lon, row["latitude"], row["longitude"])
        if distance <= radius_km:
            located.append((distance, row))
    located.sort(key=lambda pair: pair[0])
    selected = located[:max(1, min(limit, 200))]
    output = _listing_rows(con, [row for _, row in selected])
    for item, (distance, _) in zip(output, selected):
        item["distance_km"] = round(distance, 2)
    return output
