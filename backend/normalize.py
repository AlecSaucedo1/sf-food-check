from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Iterable


def _nk(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def pick(row: dict[str, Any], *aliases: str, default: Any = None) -> Any:
    lookup = {_nk(k): v for k, v in row.items()}
    for alias in aliases:
        key = _nk(alias)
        if key in lookup and lookup[key] not in (None, ""):
            return lookup[key]
    return default


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def iso_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text[:10] if len(text) >= 10 else text


def parse_location(row: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = as_float(pick(row, "latitude", "lat"))
    lon = as_float(pick(row, "longitude", "lon", "lng", "long"))
    if lat is not None and lon is not None:
        return lat, lon
    loc = pick(row, "location", "point", "geolocation")
    if isinstance(loc, dict):
        coords = loc.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            return as_float(coords[1]), as_float(coords[0])
        return as_float(loc.get("latitude")), as_float(loc.get("longitude"))
    if isinstance(loc, str):
        nums = re.findall(r"-?\d+(?:\.\d+)?", loc)
        if len(nums) >= 2:
            first, second = float(nums[0]), float(nums[1])
            if 35 < first < 40 and -125 < second < -120:
                return first, second
            if -125 < first < -120 and 35 < second < 40:
                return second, first
    return None, None


def split_codes(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value)
    parts = re.split(r"\s*[;,|]\s*|\s{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def normalize_status(value: Any) -> str:
    text = (str(value or "Unknown")).strip().lower()
    if "conditional" in text:
        return "Conditional Pass"
    if "clos" in text or "suspend" in text:
        return "Closure"
    if "pass" in text:
        return "Pass"
    return str(value or "Unknown").strip().title()


def inspection_key(permit_number: str, date: str | None, inspection_type: str | None, raw_id: str | None = None) -> str:
    if raw_id:
        return str(raw_id)
    payload = "|".join([permit_number or "", date or "", inspection_type or ""])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    permit = str(pick(row, "permit_number", "permit number", "permit", "facility_id", default="")).strip()
    dba = str(pick(row, "dba", "facility_name", "facility name", "business_name", "restaurant_name", default="Unknown facility")).strip()
    street = str(pick(row, "street_address", "street address", "address", "facility_address", default="")).strip()
    date = iso_date(pick(row, "inspection_date", "inspection date", "date"))
    itype = str(pick(row, "inspection_type", "inspection type", default="Inspection")).strip()
    lat, lon = parse_location(row)
    raw_id = pick(row, "row_id", "row id", ":id", "inspection_id", "inspection id")
    violation_codes = split_codes(pick(row, "violation_codes", "violation codes", "violation_code", "violation code"))
    violation_count = as_int(pick(row, "violation_count", "violation count"))
    if violation_count is None and violation_codes:
        violation_count = len(violation_codes)
    source_notes = pick(row, "inspection_notes", "inspection notes", "suspension_notes", "suspension notes")
    return {
        "inspection_id": inspection_key(permit, date, itype, str(raw_id) if raw_id else None),
        "permit_number": permit,
        "dba": dba,
        "street_address": street,
        "city": str(pick(row, "city", default="San Francisco")).strip() or "San Francisco",
        "state": str(pick(row, "state", default="CA")).strip() or "CA",
        "zip": str(pick(row, "zip", "zipcode", "postal_code", default="")).strip(),
        "analysis_neighborhood": str(pick(row, "analysis_neighborhood", "analysis neighborhood", "neighborhood", default="")).strip(),
        "supervisor_district": str(pick(row, "supervisor_district", "supervisor district", default="")).strip(),
        "inspection_date": date,
        "inspection_type": itype,
        "inspection_frequency_type": str(pick(row, "inspection_frequency_type", "inspection frequency type", default="")).strip(),
        "inspector": str(pick(row, "inspector", "inspector_name", "inspector name", default="")).strip(),
        "permit_type": str(pick(row, "permit_type", "permit type", default="")).strip(),
        "total_time_minutes": as_int(pick(row, "total_time_minutes", "total time minutes", "total_time", "total time")),
        "facility_rating_status": normalize_status(pick(row, "facility_rating_status", "facility rating status", "status", "inspection_status")),
        "violation_count": violation_count or 0,
        "violation_codes": violation_codes,
        "latitude": lat,
        "longitude": lon,
        "data_as_of": str(pick(row, "data_as_of", "data as of", default="")).strip(),
        "raw_row_id": str(raw_id or ""),
        "source_notes": str(source_notes or "").strip(),
        "raw": row,
    }
