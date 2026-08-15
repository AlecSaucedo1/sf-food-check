from __future__ import annotations

import os
from typing import Any

import httpx

DATASET_ID = os.getenv("DATASF_DATASET_ID", "tvy3-wexg")
BASE_URL = os.getenv("DATASF_BASE_URL", "https://data.sfgov.org/resource")


def source_url() -> str:
    return f"{BASE_URL}/{DATASET_ID}.json"


async def fetch_rows(limit: int = 5000, offset: int = 0) -> list[dict[str, Any]]:
    headers = {"Accept": "application/json", "User-Agent": "SFFoodCheck/0.1"}
    token = os.getenv("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    params = {"$limit": str(limit), "$offset": str(offset), "$order": ":id"}
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        response = await client.get(source_url(), params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("Unexpected DataSF response shape")
        return data


async def fetch_all(page_size: int = 5000, max_rows: int = 100_000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < max_rows:
        page = await fetch_rows(limit=page_size, offset=offset)
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows
