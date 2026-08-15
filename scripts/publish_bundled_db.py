from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.observations import ensure_observation_schema


BUNDLE_DB = Path(os.getenv("BUNDLED_DATABASE_PATH", "/app/data/complete-inspections.db"))
BUNDLE_SNAPSHOT = BUNDLE_DB.with_name("leaderboard_facilities.json")
ACTIVE_DB = Path(os.getenv("ACTIVE_DATABASE_PATH", "/var/data/active.db"))
LEGACY_DB = Path(os.getenv("LEGACY_DATABASE_PATH", "/var/data/inspections.db"))
LIVE_SNAPSHOT = Path(os.getenv("LEADERBOARD_SNAPSHOT_PATH", "/var/data/leaderboard_facilities.json"))


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def existing_database() -> Path | None:
    if ACTIVE_DB.is_symlink():
        target = Path(os.path.realpath(ACTIVE_DB))
        if target.exists():
            return target
    if ACTIVE_DB.exists():
        return ACTIVE_DB
    if LEGACY_DB.exists():
        return LEGACY_DB
    return None


def table_exists(con: sqlite3.Connection, schema: str, table: str) -> bool:
    row = con.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def columns(con: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [str(row[1]) for row in con.execute(f"PRAGMA {schema}.table_info({table})").fetchall()]


def preserve_enrichment(new_db: Path, old_db: Path | None) -> None:
    if not old_db or not old_db.exists() or old_db.resolve() == new_db.resolve():
        return

    with sqlite3.connect(new_db) as con:
        ensure_observation_schema(con)
        con.execute("ATTACH DATABASE ? AS previous", (str(old_db),))
        try:
            for table in ("report_enrichment", "violations", "violation_observations"):
                if not table_exists(con, "main", table) or not table_exists(con, "previous", table):
                    continue
                main_cols = columns(con, "main", table)
                old_cols = set(columns(con, "previous", table))
                common = [name for name in main_cols if name in old_cols and name != "id"]
                if not common:
                    continue
                quoted = ",".join(f'"{name}"' for name in common)
                where = ""
                if "inspection_id" in common:
                    where = " WHERE inspection_id IN (SELECT inspection_id FROM main.inspections)"
                con.execute(
                    f"INSERT OR IGNORE INTO main.{table} ({quoted}) SELECT {quoted} FROM previous.{table}{where}"
                )
            con.commit()
        finally:
            con.execute("DETACH DATABASE previous")


def atomic_copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    shutil.copy2(source, temp)
    os.replace(temp, destination)


def atomic_copy_database(source: Path, destination: Path) -> None:
    """Create a consistent standalone SQLite copy, including any WAL pages."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    for candidate in (temp, Path(str(temp) + "-wal"), Path(str(temp) + "-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass

    source_uri = f"file:{source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as src, sqlite3.connect(temp) as dst:
        src.backup(dst)
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dst.commit()
    os.replace(temp, destination)


def publish_symlink(target: Path) -> None:
    ACTIVE_DB.parent.mkdir(parents=True, exist_ok=True)
    temp_link = ACTIVE_DB.with_name(ACTIVE_DB.name + ".next")
    try:
        temp_link.unlink()
    except FileNotFoundError:
        pass
    os.symlink(target.name, temp_link)
    os.replace(temp_link, ACTIVE_DB)


def prune_versions(current: Path, keep: int = 2) -> None:
    candidates = sorted(
        ACTIVE_DB.parent.glob("inspections-bundle-*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    kept = 0
    for path in candidates:
        if path.resolve() == current.resolve():
            continue
        if kept < keep:
            kept += 1
            continue
        try:
            path.unlink()
        except OSError:
            pass


def main() -> None:
    if not BUNDLE_DB.exists():
        raise RuntimeError(f"Bundled complete database is missing: {BUNDLE_DB}")
    if not BUNDLE_SNAPSHOT.exists():
        raise RuntimeError(f"Bundled leaderboard snapshot is missing: {BUNDLE_SNAPSHOT}")

    tag = fingerprint(BUNDLE_DB)
    target = ACTIVE_DB.parent / f"inspections-bundle-{tag}.db"
    previous = existing_database()

    if not target.exists():
        atomic_copy_database(BUNDLE_DB, target)
        preserve_enrichment(target, previous)
        with sqlite3.connect(target) as con:
            ensure_observation_schema(con)
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.commit()

    publish_symlink(target)
    atomic_copy_file(BUNDLE_SNAPSHOT, LIVE_SNAPSHOT)
    prune_versions(target)

    with sqlite3.connect(target) as con:
        rows = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        facilities = con.execute("SELECT COUNT(DISTINCT permit_number) FROM inspections").fetchone()[0]
    print(
        f"Published bundled DataSF database {target.name}: rows={rows} facilities={facilities}",
        flush=True,
    )


if __name__ == "__main__":
    main()
