from __future__ import annotations

from pathlib import Path

from backend.store import connect, list_restaurants
from backend.sync_service import sync_once_blocking


OUTPUT = Path("/app/data/complete-inspections.db")


def _remove_sqlite(path: Path) -> None:
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _remove_sqlite(OUTPUT)
    snapshot = OUTPUT.with_name("leaderboard_facilities.json")
    try:
        snapshot.unlink()
    except FileNotFoundError:
        pass

    result = sync_once_blocking(str(OUTPUT), page_size=5000, max_rows=150_000)

    with connect(str(OUTPUT)) as con:
        total = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        facilities = con.execute("SELECT COUNT(DISTINCT permit_number) FROM inspections").fetchone()[0]
        legacy = con.execute("SELECT COUNT(*) FROM inspections WHERE permit_number LIKE 'H16-%'").fetchone()[0]
        historical_2020 = con.execute("SELECT COUNT(*) FROM inspections WHERE permit_number LIKE 'H20-%'").fetchone()[0]
        arsicault = list_restaurants(con, q="Arsicault", limit=200)

    addresses = {" ".join(str(row.get("street_address") or "").upper().split()) for row in arsicault}
    if total < 20_000 or facilities < 5_000:
        raise RuntimeError(f"Complete DataSF bundle failed coverage sanity check: rows={total}, facilities={facilities}")
    if legacy == 0 or historical_2020 == 0:
        raise RuntimeError(
            "Complete DataSF bundle is missing a historical era: "
            f"2016-2019 rows={legacy}, 2020-2023 rows={historical_2020}"
        )
    if len(arsicault) < 4 or not any("397 ARGUELLO" in address for address in addresses):
        raise RuntimeError(f"Known complete-coverage regression failed for Arsicault Bakery: {arsicault}")
    if not snapshot.exists():
        raise RuntimeError("Leaderboard snapshot was not generated with the complete database")

    print(
        "Validated complete DataSF bundle: "
        f"rows={total} facilities={facilities} legacy_rows={legacy} historical_2020_rows={historical_2020} "
        f"latest={result['latest_inspection_date']} arsicault_locations={len(arsicault)}",
        flush=True,
    )
