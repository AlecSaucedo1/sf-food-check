from __future__ import annotations

import csv
import io
import os
from typing import Any

import httpx

DATASET_ID = os.getenv("DATASF_DATASET_ID", "tvy3-wexg")
BASE_URL = os.getenv("DATASF_BASE_URL", "https://data.sfgov.org/resource")
DOMAIN = "https://data.sfgov.org"


def source_url() -> str:
    return f"{BASE_URL}/{DATASET_ID}.json"


def bulk_csv_url() -> str:
    # Official Socrata bulk export. This is a fallback for cases where the SODA
    # resource endpoint is throttled or temporarily rejects paginated requests.
    return f"{DOMAIN}/api/v3/views/{DATASET_ID}/export.csv?accessType=DOWNLOAD"


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "SFFoodCheck/0.3 (+https://sf-food-check.onrender.com)",
    }
    token = os.getenv("SOCRATA_APP_TOKEN", "").strip()
    if token:
        headers["X-App-Token"] = token
    return headers


async def fetch_rows(limit: int = 5000, offset: int = 0) -> list[dict[str, Any]]:
    """Fetch one page from DataSF's public SODA endpoint.

    A Socrata app token is optional. We intentionally avoid relying on Socrata's
    internal ``:id`` column for ordering because some published views do not expose
    that system field consistently.
    """
    params = {
        "$limit": str(limit),
        "$offset": str(offset),
        "$order": "inspection_date DESC, permit_number ASC, dba ASC",
    }
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(source_url(), params=params, headers=_headers())
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("Unexpected DataSF response shape")
        return data


async def fetch_bulk_csv(max_rows: int = 100_000) -> list[dict[str, Any]]:
    headers = {
        "Accept": "text/csv,*/*;q=0.8",
        "User-Agent": "SFFoodCheck/0.3 (+https://sf-food-check.onrender.com)",
    }
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.get(bulk_csv_url(), headers=headers)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        rows: list[dict[str, Any]] = []
        for row in reader:
            rows.append(dict(row))
            if len(rows) >= max_rows:
                break
        if not rows:
            raise RuntimeError("DataSF bulk export returned no rows")
        return rows


async def fetch_all(page_size: int = 5000, max_rows: int = 100_000) -> list[dict[str, Any]]:
    """Fetch the current SF inspection dataset without requiring authentication.

    The normal path uses SODA pagination. If that fails for any HTTP/network reason,
    fall back to the official bulk CSV export so a production deploy does not depend
    on a Socrata app token or one API representation.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    try:
        while offset < max_rows:
            page = await fetch_rows(limit=min(page_size, max_rows - offset), offset=offset)
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        if rows:
            return rows
    except Exception as exc:
        print(f"DataSF SODA pagination failed; trying bulk CSV export: {exc}", flush=True)

    return await fetch_bulk_csv(max_rows=max_rows)
