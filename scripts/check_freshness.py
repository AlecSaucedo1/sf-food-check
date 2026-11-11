"""Check official DataSF revision against the last successful published build.

Used by a scheduled GitHub workflow, never in the live web request path.
Checks source data_loaded_at (not max inspection_date, which has bad future dates).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


BASE = os.getenv("DATASF_BASE_URL", "https://data.sfgov.org/resource").rstrip("/")
HEALTH_URL = os.getenv("SFFOODCHECK_HEALTH_URL", "https://sf-food-check.onrender.com/api/health")
OUTPUT = Path(os.getenv("REFRESH_REVISION_PATH", "data/refresh_revision.json"))


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def needs_refresh(source_loaded_at: str, last_successful_sync: str | None, force: bool = False) -> bool:
    if force or not last_successful_sync:
        return True
    return _parse_time(source_loaded_at) > _parse_time(last_successful_sync)


def check_revision(client: httpx.Client, *, force: bool = False) -> dict:
    upstream = client.get(
        f"{BASE}/tvy3-wexg.json",
        params={"$select": "max(data_loaded_at) as latest_load, count(*) as row_count"},
    )
    upstream.raise_for_status()
    records = upstream.json()
    if not isinstance(records, list) or not records or not records[0].get("latest_load"):
        raise RuntimeError("DataSF did not provide a usable revision; refusing silent success")
    source_loaded = str(records[0]["latest_load"])
    source_rows = int(records[0]["row_count"])
    if source_rows < 20_000:
        raise RuntimeError(f"DataSF row count {source_rows} unexpectedly small")

    published_at = None
    try:
        live = client.get(HEALTH_URL, headers={"Cache-Control": "no-cache"})
        live.raise_for_status()
        health = live.json()
        sync = health.get("last_sync") or {}
        if sync.get("success"):
            published_at = sync.get("completed_at")
    except (httpx.HTTPError, ValueError):
        # Unavailable live site needs deployment too; don't mark it fresh.
        pass

    return {
        "required": needs_refresh(source_loaded, published_at, force),
        "source_loaded_at": source_loaded,
        "source_rows": source_rows,
        "live_last_sync": published_at,
    }


def main() -> None:
    force = os.getenv("FORCE_REFRESH", "false").lower() in ("true", "1", "yes")
    with httpx.Client(timeout=35, follow_redirects=True) as client:
        result = check_revision(client, force=force)
    print(f"DataSF revision check: {result}", flush=True)
    if result["required"]:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps({
            "source_dataset": "tvy3-wexg",
            "source_loaded_at": result["source_loaded_at"],
            "source_rows": result["source_rows"],
            "requested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=2) + "\n", encoding="utf-8")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"refresh_required={'true' if result['required'] else 'false'}\n")


if __name__ == "__main__":
    main()
