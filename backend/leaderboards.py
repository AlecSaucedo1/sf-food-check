from __future__ import annotations

import json
import os
import re
import statistics
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .taxonomy import assess_inspection, assess_violation, extract_source_violations, parse_grouped_findings

RISK_MODEL_VERSION = "2026.08.14.3"
_GENERIC_CHAIN_NAMES = {
    "BAR", "BAKERY", "CAFE", "COFFEE", "DELI", "GRILL", "KITCHEN", "MARKET", "RESTAURANT",
}
_CHAIN_ALIASES = {
    "STARBUCKSCOFFEE": ("STARBUCKS", "STARBUCKS"),
    "STARBUCKS": ("STARBUCKS", "STARBUCKS"),
    "MCDONALDS": ("MCDONALDS", "MCDONALD'S"),
}
_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def leaderboard_snapshot_path(db_path: str) -> str:
    return str(Path(db_path).with_name("leaderboard_facilities.json"))


def chain_identity(dba: str) -> tuple[str, str] | None:
    """Return a conservative chain key and display name from a DataSF DBA."""
    label = unicodedata.normalize("NFKC", _clean_text(dba)).upper()
    if not label:
        return None

    label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
    label = re.sub(r"\s+(?:STORE|LOCATION|UNIT)\s*#?\s*[A-Z0-9-]+\s*$", "", label).strip()
    label = re.sub(r"\s+#\s*[A-Z0-9-]+\s*$", "", label).strip()
    label = re.sub(r"\s+NO\.?\s*[A-Z0-9-]+\s*$", "", label).strip()
    label = re.sub(r"\s+\d{2,6}[A-Z]?\s*$", "", label).strip()

    if not label or label in _GENERIC_CHAIN_NAMES:
        return None

    key = re.sub(r"[^A-Z0-9]+", "", label)
    if len(key) < 4:
        return None
    return _CHAIN_ALIASES.get(key, (key, label))


def _dedupe_assessed(
    items: list[dict[str, Any]],
    assessment_cache: dict[tuple[str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    assessed: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    seen_desc: set[str] = set()
    for item in items:
        raw_code = _clean_text(item.get("code"))
        raw_desc = _clean_text(item.get("official_description"))
        raw_risk = _clean_text(item.get("official_risk_category") or item.get("risk_level"))
        cache_key = (raw_code, raw_desc, raw_risk)
        derived = assessment_cache.get(cache_key)
        if derived is None:
            derived = assess_violation(
                raw_desc or raw_code,
                official_description=raw_desc or None,
                code=raw_code or None,
                official_risk_category=raw_risk or None,
                source_field=item.get("source_field"),
            )
            assessment_cache[cache_key] = derived

        code = _clean_text(derived.get("code")).lower()
        desc = _clean_text(derived.get("official_description")).lower()
        if code and code in seen_codes:
            continue
        if not code and desc and desc in seen_desc:
            continue
        if code:
            seen_codes.add(code)
        if desc:
            seen_desc.add(desc)
        assessed.append(derived)
    return assessed


def _fast_status_only_risk(status: str) -> tuple[int, str]:
    if status == "Closure":
        return 95, "Critical"
    if status == "Conditional Pass":
        return 80, "High"
    return 0, "No cited risk"


def _source_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        raw = json.loads(data.get("raw_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raw = {}

    raw_violation = raw.get("violation_codes") if isinstance(raw, dict) else None
    if raw_violation:
        grouped = parse_grouped_findings(raw_violation)
        if grouped:
            return [{**item, "source_field": "violation_codes"} for item in grouped]

    try:
        fallback_codes = json.loads(data.get("violation_codes_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        fallback_codes = []
    return extract_source_violations(raw, fallback_codes)


def _latest_scored_facilities(con, months: int) -> list[dict[str, Any]]:
    cutoff = (date.today() - timedelta(days=round(months * 30.4375))).isoformat()
    rows = con.execute(
        """
        WITH ranked AS (
          SELECT
            inspection_id, permit_number, dba, street_address, analysis_neighborhood,
            inspection_date, facility_rating_status, violation_count,
            violation_codes_json, raw_json,
            ROW_NUMBER() OVER (
              PARTITION BY permit_number ORDER BY inspection_date DESC, inspection_id DESC
            ) AS rn
          FROM inspections
          WHERE inspection_date >= ?
            AND facility_rating_status IN ('Pass', 'Conditional Pass', 'Closure')
        )
        SELECT * FROM ranked WHERE rn=1
        """,
        (cutoff,),
    ).fetchall()

    manual: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if con.execute("SELECT EXISTS(SELECT 1 FROM violations LIMIT 1)").fetchone()[0]:
        for row in con.execute(
            "SELECT inspection_id, code, official_description, risk_level FROM violations"
        ).fetchall():
            manual[row["inspection_id"]].append({
                "code": row["code"],
                "official_description": row["official_description"],
                "official_risk_category": row["risk_level"],
                "source_field": "violations_table",
            })

    facilities: list[dict[str, Any]] = []
    assessment_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        status = data["facility_rating_status"]
        published_count = int(data.get("violation_count") or 0)

        if published_count == 0 and not manual.get(data["inspection_id"]):
            score, level = _fast_status_only_risk(status)
            mapped_count = 0
        else:
            candidates = list(manual.get(data["inspection_id"], []))
            candidates.extend(_source_findings(data))
            assessed = _dedupe_assessed(candidates, assessment_cache)
            mapped_count = sum(1 for item in assessed if item.get("official_description"))
            if published_count > 0 and mapped_count == 0:
                continue
            risk = assess_inspection(
                assessed,
                status=status,
                violation_count=published_count or len(assessed),
            )
            score = int(risk.get("risk_score") or 0)
            level = risk.get("risk_level") or "Low"

        facilities.append({
            "permit_number": data["permit_number"],
            "dba": data.get("dba") or "",
            "street_address": data.get("street_address") or "",
            "analysis_neighborhood": data.get("analysis_neighborhood") or "",
            "inspection_date": data.get("inspection_date") or "",
            "facility_rating_status": status,
            "risk_score": score,
            "risk_level": level,
            "mapped_count": mapped_count,
            "published_count": published_count,
        })
    return facilities


def refresh_leaderboard_snapshot(db_path: str, *, model_version: str = RISK_MODEL_VERSION) -> dict[str, Any]:
    """Precompute latest facility risk scores and atomically publish them to disk.

    This deliberately runs during the DataSF sync rather than inside an HTTP request.
    The previous snapshot remains intact until the replacement file is complete.
    """
    from .store import connect

    with connect(db_path) as con:
        # The current DataSF dataset starts in 2024. A 120-month window comfortably
        # captures every possible latest rated inspection while keeping the helper generic.
        facilities = _latest_scored_facilities(con, 120)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "model_version": model_version,
        "generated_at": generated_at,
        "facility_count": len(facilities),
        "facilities": facilities,
    }
    output = Path(leaderboard_snapshot_path(db_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="leaderboards-", suffix=".json", dir=str(output.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp_name, output)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    _CACHE.clear()
    return {"generated_at": generated_at, "facility_count": len(facilities), "path": str(output)}


def _load_snapshot(snapshot_path: str, model_version: str) -> tuple[list[dict[str, Any]], str] | None:
    path = Path(snapshot_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("model_version") != model_version or not isinstance(payload.get("facilities"), list):
        return None
    return payload["facilities"], str(payload.get("generated_at") or "")


def _summary(scores: list[int], statuses: list[str]) -> dict[str, Any]:
    return {
        "average_risk": round(sum(scores) / len(scores), 1),
        "median_risk": round(float(statistics.median(scores)), 1),
        "pass_rate": round(100 * sum(1 for status in statuses if status == "Pass") / len(statuses), 1),
    }


def _chain_leaderboard(facilities: list[dict[str, Any]], minimum_locations: int, limit: int) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for facility in facilities:
        identity = chain_identity(facility["dba"])
        if not identity:
            continue
        key, label = identity
        group = groups.setdefault(key, {"labels": Counter(), "locations": {}})
        group["labels"][label] += 1
        address_key = re.sub(r"[^A-Z0-9]+", "", facility["street_address"].upper()) or facility["permit_number"]
        existing = group["locations"].get(address_key)
        if existing is None or facility["risk_score"] > existing["risk_score"]:
            group["locations"][address_key] = facility

    leaderboard = []
    for group in groups.values():
        locations = list(group["locations"].values())
        if len(locations) < minimum_locations:
            continue
        scores = [item["risk_score"] for item in locations]
        statuses = [item["facility_rating_status"] for item in locations]
        leaderboard.append({
            "name": group["labels"].most_common(1)[0][0],
            "location_count": len(locations),
            "latest_inspection_date": max(item["inspection_date"] for item in locations),
            **_summary(scores, statuses),
        })

    leaderboard.sort(key=lambda item: (item["average_risk"], -item["pass_rate"], -item["location_count"], item["name"]))
    return leaderboard[:limit]


def _neighborhood_leaderboard(facilities: list[dict[str, Any]], minimum_restaurants: int, limit: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for facility in facilities:
        neighborhood = _clean_text(facility["analysis_neighborhood"])
        if neighborhood:
            groups[neighborhood].append(facility)

    leaderboard = []
    for name, items in groups.items():
        if len(items) < minimum_restaurants:
            continue
        scores = [item["risk_score"] for item in items]
        statuses = [item["facility_rating_status"] for item in items]
        leaderboard.append({
            "name": name,
            "restaurant_count": len(items),
            "latest_inspection_date": max(item["inspection_date"] for item in items),
            **_summary(scores, statuses),
        })

    leaderboard.sort(key=lambda item: (item["average_risk"], -item["pass_rate"], -item["restaurant_count"], item["name"]))
    return leaderboard[:limit]


def build_leaderboards(
    con,
    *,
    model_version: str,
    months: int = 18,
    minimum_chain_locations: int = 3,
    minimum_neighborhood_restaurants: int = 25,
    limit: int = 10,
    snapshot_path: str = "",
) -> dict[str, Any]:
    snapshot = _load_snapshot(snapshot_path, model_version) if snapshot_path else None
    generated_at = ""
    if snapshot:
        all_facilities, generated_at = snapshot
        cutoff = (date.today() - timedelta(days=round(months * 30.4375))).isoformat()
        facilities = [item for item in all_facilities if str(item.get("inspection_date") or "") >= cutoff]
        source_marker: tuple[Any, ...] = (snapshot_path, generated_at, len(all_facilities))
    else:
        latest = con.execute("SELECT MAX(inspection_date) FROM inspections").fetchone()[0]
        row_count = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        facilities = _latest_scored_facilities(con, months)
        source_marker = (latest, row_count)

    cache_key = (
        *source_marker, model_version, months, minimum_chain_locations,
        minimum_neighborhood_restaurants, limit,
    )
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    result = {
        "chains": _chain_leaderboard(facilities, minimum_chain_locations, limit),
        "neighborhoods": _neighborhood_leaderboard(facilities, minimum_neighborhood_restaurants, limit),
        "methodology": {
            "metric": "Average Foodborne Illness Risk Index",
            "direction": "lower_is_better",
            "months": months,
            "minimum_chain_locations": minimum_chain_locations,
            "minimum_neighborhood_restaurants": minimum_neighborhood_restaurants,
            "eligible_facilities": len(facilities),
            "snapshot_generated_at": generated_at or None,
            "note": "Uses each facility's most recent rated inspection in the window. Cited violations without descriptive findings are excluded from comparative rankings rather than assigned a guessed severity.",
            "model_version": model_version,
        },
    }
    _CACHE.clear()
    _CACHE[cache_key] = result
    return result
