from __future__ import annotations

import json
import os
import re
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .leaderboards import _bulk_assess, _source_findings, chain_identity
from .scoring_v2 import RISK_MODEL_VERSION, assess_inspection, calibrate_score, calibrate_violation_item, risk_band

_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def leaderboard_snapshot_path(db_path: str) -> str:
    return str(Path(db_path).with_name("leaderboard_facilities.json"))


def _latest_scored_facilities(con, months: int) -> list[dict[str, Any]]:
    cutoff = (date.today() - timedelta(days=round(months * 30.4375))).isoformat()
    rows = con.execute(
        """
        WITH ranked AS (
          SELECT
            inspection_id, permit_number, dba, street_address, analysis_neighborhood,
            inspection_date, facility_rating_status, violation_count, raw_json,
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
            if status == "Closure":
                score, level = 92, "Critical"
            elif status == "Conditional Pass":
                score, level = 70, "High"
            else:
                score, level = 0, "No cited risk"
            mapped_count = 0
        else:
            candidates = list(manual.get(data["inspection_id"], []))
            candidates.extend(_source_findings(data))
            legacy_assessed = _bulk_assess(candidates, assessment_cache)
            assessed = [calibrate_violation_item(item) for item in legacy_assessed]
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
    """Build a read-only facility score snapshot and atomically replace the old file."""
    from .store import connect

    with connect(db_path) as con:
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


def _load_snapshot(snapshot_path: str) -> tuple[list[dict[str, Any]], str, str, bool] | None:
    path = Path(snapshot_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    facilities = payload.get("facilities")
    if not isinstance(facilities, list):
        return None

    source_version = str(payload.get("model_version") or "unknown")
    recalibrated = source_version != RISK_MODEL_VERSION
    if recalibrated:
        # Keep the leaderboard responsive during a deploy while the new snapshot is
        # rebuilding. This monotonic transformation is transitional; the background
        # refresh replaces it with exact v2 facility scores shortly after startup.
        converted = []
        for item in facilities:
            row = dict(item)
            score = calibrate_score(row.get("risk_score"))
            row["risk_score"] = score
            row["risk_level"] = risk_band(score)
            converted.append(row)
        facilities = converted

    return facilities, str(payload.get("generated_at") or ""), source_version, recalibrated


def _summary(scores: list[int], statuses: list[str]) -> dict[str, Any]:
    total = len(scores)
    return {
        "average_risk": round(sum(scores) / total, 1),
        "median_risk": round(float(statistics.median(scores)), 1),
        "pass_rate": round(100 * sum(1 for status in statuses if status == "Pass") / total, 1),
        "conditional_rate": round(100 * sum(1 for status in statuses if status == "Conditional Pass") / total, 1),
        "closure_rate": round(100 * sum(1 for status in statuses if status == "Closure") / total, 1),
    }


def _chain_groups(facilities: list[dict[str, Any]], minimum_locations: int) -> list[dict[str, Any]]:
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

    result = []
    for group in groups.values():
        locations = list(group["locations"].values())
        if len(locations) < minimum_locations:
            continue
        scores = [int(item["risk_score"]) for item in locations]
        statuses = [item["facility_rating_status"] for item in locations]
        result.append({
            "name": group["labels"].most_common(1)[0][0],
            "location_count": len(locations),
            "latest_inspection_date": max(item["inspection_date"] for item in locations),
            **_summary(scores, statuses),
        })
    return result


def _neighborhood_groups(facilities: list[dict[str, Any]], minimum_restaurants: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for facility in facilities:
        neighborhood = _clean_text(facility["analysis_neighborhood"])
        if neighborhood:
            groups[neighborhood].append(facility)

    result = []
    for name, items in groups.items():
        if len(items) < minimum_restaurants:
            continue
        scores = [int(item["risk_score"]) for item in items]
        statuses = [item["facility_rating_status"] for item in items]
        result.append({
            "name": name,
            "restaurant_count": len(items),
            "latest_inspection_date": max(item["inspection_date"] for item in items),
            **_summary(scores, statuses),
        })
    return result


def _best(items: list[dict[str, Any]], count_key: str, limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        items,
        key=lambda item: (item["average_risk"], -item["pass_rate"], -item[count_key], item["name"]),
    )
    return ranked[:limit]


def _highest_risk(items: list[dict[str, Any]], count_key: str, limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        items,
        key=lambda item: (-item["average_risk"], item["pass_rate"], -item[count_key], item["name"]),
    )
    return ranked[:limit]


def build_leaderboards(
    con,
    *,
    model_version: str = RISK_MODEL_VERSION,
    months: int = 18,
    minimum_chain_locations: int = 3,
    minimum_neighborhood_restaurants: int = 25,
    limit: int = 10,
    snapshot_path: str = "",
) -> dict[str, Any]:
    snapshot = _load_snapshot(snapshot_path) if snapshot_path else None
    generated_at = ""
    source_version = model_version
    recalibrated_snapshot = False

    if snapshot:
        all_facilities, generated_at, source_version, recalibrated_snapshot = snapshot
        cutoff = (date.today() - timedelta(days=round(months * 30.4375))).isoformat()
        facilities = [item for item in all_facilities if str(item.get("inspection_date") or "") >= cutoff]
        source_marker: tuple[Any, ...] = (snapshot_path, generated_at, source_version, len(all_facilities))
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

    chain_groups = _chain_groups(facilities, minimum_chain_locations)
    neighborhood_groups = _neighborhood_groups(facilities, minimum_neighborhood_restaurants)
    result = {
        # Backward-compatible best-score keys.
        "chains": _best(chain_groups, "location_count", limit),
        "neighborhoods": _best(neighborhood_groups, "restaurant_count", limit),
        # Reverse leaderboard requested by the product owner.
        "highest_risk_chains": _highest_risk(chain_groups, "location_count", limit),
        "highest_risk_neighborhoods": _highest_risk(neighborhood_groups, "restaurant_count", limit),
        "methodology": {
            "metric": "Average Foodborne Illness Risk Index",
            "direction": "lower_is_better",
            "reverse_direction": "higher_is_worse",
            "months": months,
            "minimum_chain_locations": minimum_chain_locations,
            "minimum_neighborhood_restaurants": minimum_neighborhood_restaurants,
            "eligible_facilities": len(facilities),
            "snapshot_generated_at": generated_at or None,
            "snapshot_model_version": source_version,
            "snapshot_recalibrated_during_deploy": recalibrated_snapshot,
            "note": (
                "Uses each facility's most recent rated inspection in the window. Cited violations without descriptive "
                "findings are excluded rather than assigned a guessed severity. Best lists sort lower risk first; reverse "
                "lists sort higher risk first using the same eligibility thresholds."
            ),
            "model_version": model_version,
        },
    }
    _CACHE.clear()
    _CACHE[cache_key] = result
    return result
