from __future__ import annotations

import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from .taxonomy import assess_inspection, assess_violation, extract_source_violations, parse_grouped_findings

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
    """Use the known current DataSF violation shape before the generic parser.

    This function is only called for inspections with cited violations. Most latest
    inspections have no violations, so the leaderboard avoids JSON/regex work for
    the large majority of facilities.
    """
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

        # The common case: no cited violations. Avoid JSON parsing and taxonomy
        # evaluation altogether while preserving the status floors used by the
        # full inspection model.
        if published_count == 0 and not manual.get(data["inspection_id"]):
            score, level = _fast_status_only_risk(status)
            mapped_count = 0
        else:
            candidates = list(manual.get(data["inspection_id"], []))
            candidates.extend(_source_findings(data))
            assessed = _dedupe_assessed(candidates, assessment_cache)
            mapped_count = sum(1 for item in assessed if item.get("official_description"))

            # A cited violation with no descriptive finding can look artificially safe.
            # Exclude it from comparative rankings rather than guessing its severity.
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
) -> dict[str, Any]:
    latest = con.execute("SELECT MAX(inspection_date) FROM inspections").fetchone()[0]
    row_count = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
    cache_key = (
        latest, row_count, model_version, months, minimum_chain_locations,
        minimum_neighborhood_restaurants, limit,
    )
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    facilities = _latest_scored_facilities(con, months)
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
            "note": "Uses each facility's most recent rated inspection in the window. Cited violations without descriptive findings are excluded from comparative rankings rather than assigned a guessed severity.",
            "model_version": model_version,
        },
    }
    _CACHE.clear()
    _CACHE[cache_key] = result
    return result
