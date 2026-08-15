from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from typing import Any

import httpx

from .datasf import fetch_all as fetch_current_all

HISTORICAL_2020_DATASET_ID = "5tti-66ds"
LEGACY_2016_DATASET_ID = "pyih-qa8i"
BASE_URL = os.getenv("DATASF_BASE_URL", "https://data.sfgov.org/resource")


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "SFFoodCheck/0.9 (+https://sf-food-check.onrender.com)",
    }
    token = os.getenv("SOCRATA_APP_TOKEN", "").strip()
    if token:
        headers["X-App-Token"] = token
    return headers


def _key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _facility_seed(name: Any, address: Any) -> str:
    payload = f"{_key(name)}|{_key(address)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


async def _fetch_dataset(
    dataset_id: str,
    *,
    order_field: str,
    page_size: int = 5000,
    max_rows: int = 150_000,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        while offset < max_rows:
            params = {
                "$limit": str(min(page_size, max_rows - offset)),
                "$offset": str(offset),
                "$order": f"{order_field} DESC",
            }
            response = await client.get(
                f"{BASE_URL}/{dataset_id}.json",
                params=params,
                headers=_headers(),
            )
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list):
                raise RuntimeError(f"Unexpected DataSF response shape for {dataset_id}")
            rows.extend(page)
            if len(page) < int(params["$limit"]):
                break
            offset += len(page)
    return rows


def _aggregate_2020(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    findings: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        inspection_id = str(row.get("inspection_id") or "").strip()
        if not inspection_id:
            continue
        name = str(row.get("name") or "Unknown facility").strip()
        address = str(row.get("address") or "").strip()
        permit = f"H20-{_facility_seed(name, address)}"
        target = grouped.setdefault(inspection_id, {
            "inspection_id": f"H20:{inspection_id}",
            "permit_number": permit,
            "dba": name,
            "street_address": address,
            "city": row.get("city") or "San Francisco",
            "state": row.get("state") or "CA",
            "zip": row.get("postal_code") or "",
            "inspection_date": row.get("date"),
            "inspection_type": row.get("inspection_type") or "Inspection",
            "facility_rating_status": row.get("facility_status") or "Unknown",
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "source_dataset": HISTORICAL_2020_DATASET_ID,
            "source_period": "2020-2023",
        })
        description = " ".join(str(row.get("description") or "").split())
        observed = " ".join(str(row.get("violation_observed") or "").split())
        if description:
            finding = description if not observed else f"{description} [{observed}]"
            if finding not in findings[inspection_id]:
                findings[inspection_id].append(finding)
        if not target.get("latitude") and row.get("latitude"):
            target["latitude"] = row.get("latitude")
        if not target.get("longitude") and row.get("longitude"):
            target["longitude"] = row.get("longitude")

    output = []
    for inspection_id, row in grouped.items():
        row["violation_codes"] = findings[inspection_id]
        row["violation_count"] = len(findings[inspection_id])
        output.append(row)
    return output


def _aggregate_legacy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    findings: dict[str, list[str]] = defaultdict(list)
    risk_categories: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        inspection_id = str(row.get("inspection_id") or "").strip()
        if not inspection_id:
            continue
        business_id = str(row.get("business_id") or "").strip()
        name = str(row.get("business_name") or "Unknown facility").strip()
        address = str(row.get("business_address") or "").strip()
        permit = f"H16-{business_id or _facility_seed(name, address)}"
        target = grouped.setdefault(inspection_id, {
            "inspection_id": f"H16:{inspection_id}",
            "permit_number": permit,
            "dba": name,
            "street_address": address,
            "city": row.get("business_city") or "San Francisco",
            "state": row.get("business_state") or "CA",
            "zip": row.get("business_postal_code") or "",
            "inspection_date": row.get("inspection_date"),
            "inspection_type": row.get("inspection_type") or "Inspection",
            # The 2016-2019 LIVES era used a numeric official score rather than
            # today's Pass / Conditional Pass / Closure placards. Do not invent a
            # modern status for those inspections.
            "facility_rating_status": "Historical",
            "source_notes": f"Legacy SFDPH inspection score: {row.get('inspection_score', 'N/A')}",
            "legacy_inspection_score": row.get("inspection_score"),
            "source_dataset": LEGACY_2016_DATASET_ID,
            "source_period": "2016-2019",
        })
        description = " ".join(str(row.get("violation_description") or "").split())
        violation_id = str(row.get("violation_id") or "").strip()
        code = violation_id.rsplit("_", 1)[-1] if violation_id and "_" in violation_id else violation_id
        if description:
            finding = f"{code} - {description}" if code else description
            if finding not in findings[inspection_id]:
                findings[inspection_id].append(finding)
                risk_categories[inspection_id].append(str(row.get("risk_category") or ""))
        if not target.get("legacy_inspection_score") and row.get("inspection_score"):
            target["legacy_inspection_score"] = row.get("inspection_score")

    output = []
    for inspection_id, row in grouped.items():
        row["violation_codes"] = findings[inspection_id]
        row["violation_count"] = len(findings[inspection_id])
        row["violation_risk_category"] = risk_categories[inspection_id]
        output.append(row)
    return output


def _reconcile_with_current(
    current_rows: list[dict[str, Any]],
    historical_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    by_clean_identity: dict[tuple[str, str], dict[str, Any]] = {}

    for row in current_rows:
        name_key = _key(row.get("dba"))
        address = row.get("street_address")
        clean_address = row.get("street_address_clean") or address
        if not name_key:
            continue
        payload = {
            "permit_number": str(row.get("permit_number") or "").strip(),
            "analysis_neighborhood": row.get("analysis_neighborhood") or "",
            "supervisor_district": row.get("supervisor_district") or "",
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
        }
        if _key(address):
            by_identity[(_key(address), name_key)] = payload
        if _key(clean_address):
            by_clean_identity[(_key(clean_address), name_key)] = payload

    output: list[dict[str, Any]] = []
    for row in historical_rows:
        name_key = _key(row.get("dba"))
        address_key = _key(row.get("street_address"))
        match = by_identity.get((address_key, name_key)) or by_clean_identity.get((address_key, name_key))
        if match and match.get("permit_number"):
            row = dict(row)
            row["permit_number"] = match["permit_number"]
            row["analysis_neighborhood"] = row.get("analysis_neighborhood") or match.get("analysis_neighborhood") or ""
            row["supervisor_district"] = row.get("supervisor_district") or match.get("supervisor_district") or ""
            row["latitude"] = row.get("latitude") or match.get("latitude")
            row["longitude"] = row.get("longitude") or match.get("longitude")
        output.append(row)
    return output


async def fetch_complete_history(
    *,
    page_size: int = 5000,
    max_rows: int = 150_000,
) -> list[dict[str, Any]]:
    """Return one unified DataSF inspection history across all official eras.

    Current records remain authoritative. Historical inspections are normalized to
    the current storage shape and reconciled onto a current permit when the DBA and
    street address match exactly after normalization. Otherwise they retain a stable
    synthetic historical permit so the location remains searchable.
    """
    current = await fetch_current_all(page_size=page_size, max_rows=max_rows)
    historical_2020_raw = await _fetch_dataset(
        HISTORICAL_2020_DATASET_ID,
        order_field="date",
        page_size=page_size,
        max_rows=max_rows,
    )
    legacy_raw = await _fetch_dataset(
        LEGACY_2016_DATASET_ID,
        order_field="inspection_date",
        page_size=page_size,
        max_rows=max_rows,
    )

    historical = _aggregate_2020(historical_2020_raw) + _aggregate_legacy(legacy_raw)
    historical = _reconcile_with_current(current, historical)
    return current + historical
