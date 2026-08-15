from __future__ import annotations

import json
import math
import sqlite3
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


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert_inspections(con: sqlite3.Connection, rows: list[dict[str, Any]], *, commit: bool = True) -> int:
    normalized = [normalize_row(r) for r in rows]
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
        con.commit()
    return len(normalized)


def replace_inspections(con: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM violations")
        con.execute("DELETE FROM inspections")
        count = upsert_inspections(con, rows, commit=False)
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
    # The live DataSF dataset is inspection-grained. Recover violation details from
    # the raw source row instead of assuming the separate `violations` table is filled.
    data["source_violations"] = extract_source_violations(raw_source, data["violation_codes"])
    data["source_violation_fields"] = sorted(
        str(k) for k in raw_source.keys() if "violation" in str(k).lower()
    )

    enrich = con.execute("SELECT report_url, inspector_comments, corrective_action, comment_source, source_label FROM report_enrichment WHERE permit_number=? AND inspection_date=?", (data["permit_number"], data["inspection_date"])).fetchone()
    data["report"] = dict(enrich) if enrich else None
    violations = con.execute("SELECT code, official_description, normalized_category, consumer_description, risk_level, inspector_comment FROM violations WHERE inspection_id=?", (data["inspection_id"],)).fetchall()
    data["violations"] = [dict(v) for v in violations]
    return data


def list_restaurants(con: sqlite3.Connection, q: str = "", status: str = "", neighborhood: str = "", limit: int = 50) -> list[dict[str, Any]]:
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
    sql = f"""
    WITH ranked AS (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY permit_number ORDER BY inspection_date DESC, inspection_id DESC) rn
      FROM inspections {clause}
    )
    SELECT * FROM ranked WHERE rn=1 ORDER BY inspection_date DESC, dba COLLATE NOCASE LIMIT ?
    """
    rows = con.execute(sql, (*params, max(1, min(limit, 200)))).fetchall()
    results = []
    for row in rows:
        base = dict(row)
        history = con.execute("SELECT facility_rating_status, inspection_date FROM inspections WHERE permit_number=? ORDER BY inspection_date DESC LIMIT 5", (base["permit_number"],)).fetchall()
        results.append({"permit_number": base["permit_number"], "dba": base["dba"], "street_address": base["street_address"], "analysis_neighborhood": base["analysis_neighborhood"], "facility_rating_status": base["facility_rating_status"], "inspection_date": base["inspection_date"], "violation_count": base["violation_count"], "latitude": base["latitude"], "longitude": base["longitude"], "history": [dict(h) for h in history]})
    return results


def restaurant_detail(con: sqlite3.Connection, permit_number: str) -> dict[str, Any] | None:
    rows = con.execute("SELECT * FROM inspections WHERE permit_number=? ORDER BY inspection_date DESC, inspection_id DESC", (permit_number,)).fetchall()
    if not rows:
        return None
    inspections = [_row_to_inspection(r, con) for r in rows]
    latest = inspections[0]
    return {"permit_number": permit_number, "dba": latest["dba"], "street_address": latest["street_address"], "city": latest["city"], "state": latest["state"], "zip": latest["zip"], "analysis_neighborhood": latest["analysis_neighborhood"], "latitude": latest["latitude"], "longitude": latest["longitude"], "current_status": latest["facility_rating_status"], "latest_inspection_date": latest["inspection_date"], "inspections": inspections}


def nearby(con: sqlite3.Connection, lat: float, lon: float, radius_km: float = 2.0, limit: int = 50) -> list[dict[str, Any]]:
    items = list_restaurants(con, limit=200)
    found = []
    for item in items:
        if item["latitude"] is None or item["longitude"] is None:
            continue
        d = _distance_km(lat, lon, item["latitude"], item["longitude"])
        if d <= radius_km:
            item = dict(item)
            item["distance_km"] = round(d, 2)
            found.append(item)
    return sorted(found, key=lambda x: x["distance_km"])[:limit]
