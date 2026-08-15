from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from .datasf import fetch_all
from .leaderboards import RISK_MODEL_VERSION, refresh_leaderboard_snapshot
from .store import connect, replace_inspections, record_sync_run


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store_rows_and_snapshot(db_path: str, rows: list[dict], started_at: str) -> dict:
    with connect(db_path) as con:
        count = replace_inspections(con, rows)
        facilities = con.execute("SELECT COUNT(DISTINCT permit_number) FROM inspections").fetchone()[0]
        latest = con.execute("SELECT MAX(inspection_date) FROM inspections").fetchone()[0]

    # Score the latest rated inspection for each facility once during sync. This is
    # intentionally outside the HTTP request path; the snapshot writer is atomic, so
    # an existing leaderboard remains usable until the replacement is complete.
    leaderboard = refresh_leaderboard_snapshot(db_path, model_version=RISK_MODEL_VERSION)

    completed_at = utc_now()
    with connect(db_path) as con:
        record_sync_run(
            con,
            started_at=started_at,
            completed_at=completed_at,
            success=True,
            row_count=count,
            facility_count=facilities,
            latest_inspection_date=latest,
            error="",
        )
    return {
        "ok": True,
        "rows": count,
        "facilities": facilities,
        "latest_inspection_date": latest,
        "started_at": started_at,
        "completed_at": completed_at,
        "leaderboard_facilities": leaderboard["facility_count"],
        "leaderboard_generated_at": leaderboard["generated_at"],
    }


async def sync_once(
    db_path: str,
    *,
    page_size: int = 5000,
    max_rows: int = 100_000,
    save_raw: str = "",
) -> dict:
    """Fetch a complete DataSF snapshot and replace structured inspection rows.

    The existing database is left intact if the upstream fetch fails. Report enrichment
    is stored separately and is not deleted during a structured-data refresh. Leaderboard
    facility scores are materialized during the sync so leaderboard HTTP requests remain fast.
    """
    started_at = utc_now()
    try:
        rows = await fetch_all(page_size=page_size, max_rows=max_rows)
        if not rows:
            raise RuntimeError("DataSF returned no rows; existing database was preserved.")

        if save_raw:
            import json
            Path(save_raw).parent.mkdir(parents=True, exist_ok=True)
            Path(save_raw).write_text(json.dumps(rows, ensure_ascii=False, indent=2))

        # Keep CPU-heavy normalization/scoring off the FastAPI event loop during the
        # recurring background refresh. Startup sync still waits for completion before
        # publishing the new application instance.
        return await asyncio.to_thread(_store_rows_and_snapshot, db_path, rows, started_at)
    except Exception as exc:
        try:
            with connect(db_path) as con:
                record_sync_run(
                    con,
                    started_at=started_at,
                    completed_at=utc_now(),
                    success=False,
                    row_count=0,
                    facility_count=0,
                    latest_inspection_date=None,
                    error=str(exc)[:2000],
                )
        except Exception:
            pass
        raise


def sync_once_blocking(db_path: str, **kwargs) -> dict:
    return asyncio.run(sync_once(db_path, **kwargs))
