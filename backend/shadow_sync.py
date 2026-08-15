from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .data_coverage import fetch_complete_history
from .rankings_v2 import RISK_MODEL_VERSION, refresh_leaderboard_snapshot
from .store import connect, record_sync_run, replace_inspections


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cleanup_sqlite_sidecars(path: str) -> None:
    for suffix in ("-wal", "-shm"):
        try:
            Path(path + suffix).unlink()
        except FileNotFoundError:
            pass


def _copy_live_database(source_path: str, target_path: str) -> None:
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(source_path).exists():
        with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
            source.backup(target)
    else:
        with connect(target_path):
            pass


def _publish_symlink(active_path: str, target_path: str) -> None:
    active = Path(active_path)
    target = Path(target_path)
    temp_link = active.with_name(active.name + ".next")
    try:
        temp_link.unlink()
    except FileNotFoundError:
        pass
    os.symlink(target.name, temp_link)
    os.replace(temp_link, active)


def _prune_old_versions(directory: Path, current_target: Path, keep: int = 2) -> None:
    candidates = sorted(
        directory.glob("inspections-*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    kept = 0
    for path in candidates:
        if path.resolve() == current_target.resolve():
            continue
        if kept < keep:
            kept += 1
            continue
        try:
            path.unlink()
            _cleanup_sqlite_sidecars(str(path))
        except OSError:
            pass


def _store_shadow(active_path: str, rows: list[dict], started_at: str) -> dict:
    active = Path(active_path)
    directory = active.parent
    current_target = Path(os.path.realpath(active_path))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    next_db = directory / f"inspections-{stamp}.db"

    _copy_live_database(str(current_target), str(next_db))
    with connect(str(next_db)) as con:
        count = replace_inspections(con, rows)
        facilities = con.execute("SELECT COUNT(DISTINCT permit_number) FROM inspections").fetchone()[0]
        latest = con.execute("SELECT MAX(inspection_date) FROM inspections").fetchone()[0]
        # Ensure WAL pages are folded into the versioned database before the symlink swap.
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    _cleanup_sqlite_sidecars(str(next_db))
    _publish_symlink(active_path, str(next_db))

    # New HTTP connections now resolve to the completed database. Rebuild the
    # read-only leaderboard snapshot afterward; the previous snapshot remains valid
    # until its atomic replacement completes.
    leaderboard = refresh_leaderboard_snapshot(active_path, model_version=RISK_MODEL_VERSION)

    completed_at = _utc_now()
    with connect(active_path) as con:
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

    _prune_old_versions(directory, next_db)
    return {
        "ok": True,
        "rows": count,
        "facilities": facilities,
        "latest_inspection_date": latest,
        "leaderboard_facilities": leaderboard["facility_count"],
        "started_at": started_at,
        "completed_at": completed_at,
    }


async def sync_complete_shadow(active_path: str, *, page_size: int = 5000, max_rows: int = 150_000) -> dict:
    """Build a complete DataSF database off to the side and atomically publish it."""
    started_at = _utc_now()
    try:
        rows = await fetch_complete_history(page_size=page_size, max_rows=max_rows)
        if not rows:
            raise RuntimeError("DataSF returned no inspection rows; existing database preserved")
        return await asyncio.to_thread(_store_shadow, active_path, rows, started_at)
    except Exception as exc:
        try:
            with connect(active_path) as con:
                record_sync_run(
                    con,
                    started_at=started_at,
                    completed_at=_utc_now(),
                    success=False,
                    row_count=0,
                    facility_count=0,
                    latest_inspection_date=None,
                    error=str(exc)[:2000],
                )
        except Exception:
            pass
        raise


def sync_complete_shadow_blocking(active_path: str, **kwargs) -> dict:
    return asyncio.run(sync_complete_shadow(active_path, **kwargs))
