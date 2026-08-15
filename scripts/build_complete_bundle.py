from __future__ import annotations

import os
from pathlib import Path

import httpx

from backend.store import connect, list_restaurants
from backend.sync_service import sync_once_blocking


OUTPUT = Path("/app/data/complete-inspections.db")
MAX_ROWS_PER_DATASET = 150_000
DATASETS = ("tvy3-wexg", "5tti-66ds", "pyih-qa8i")
BASE_URL = os.getenv("DATASF_BASE_URL", "https://data.sfgov.org/resource")


def _remove_sqlite(path: Path) -> None:
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _published_row_count(dataset_id: str) -> int:
    response = httpx.get(
        f"{BASE_URL}/{dataset_id}.json",
        params={"$select": "count(*) as count"},
        headers={"User-Agent": "SFFoodCheck-build/1.0"},
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"Could not verify published row count for DataSF dataset {dataset_id}")
    return int(payload[0]["count"])


if __name__ == "__main__":
    upstream_counts = {dataset_id: _published_row_count(dataset_id) for dataset_id in DATASETS}
    over_cap = {dataset_id: count for dataset_id, count in upstream_counts.items() if count > MAX_ROWS_PER_DATASET}
    if over_cap:
        raise RuntimeError(
            "Refusing to build a potentially truncated DataSF bundle. Increase MAX_ROWS_PER_DATASET first: "
            f"{over_cap}"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _remove_sqlite(OUTPUT)
    snapshot = OUTPUT.with_name("leaderboard_facilities.json")
    try:
        snapshot.unlink()
    except FileNotFoundError:
        pass

    result = sync_once_blocking(
        str(OUTPUT),
        page_size=5000,
        max_rows=MAX_ROWS_PER_DATASET,
    )

    with connect(str(OUTPUT)) as con:
        total = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        facilities = con.execute("SELECT COUNT(DISTINCT permit_number) FROM inspections").fetchone()[0]
        legacy = con.execute("SELECT COUNT(*) FROM inspections WHERE permit_number LIKE 'H16-%'").fetchone()[0]
        historical_2020 = con.execute("SELECT COUNT(*) FROM inspections WHERE permit_number LIKE 'H20-%'").fetchone()[0]
        current = con.execute("SELECT COUNT(*) FROM inspections WHERE permit_number NOT LIKE 'H16-%' AND permit_number NOT LIKE 'H20-%'").fetchone()[0]
        arsicault = list_restaurants(con, q="Arsicault", limit=200)

    addresses = {" ".join(str(row.get("street_address") or "").upper().split()) for row in arsicault}
    if total < 20_000 or facilities < 5_000:
        raise RuntimeError(f"Complete DataSF bundle failed coverage sanity check: rows={total}, facilities={facilities}")
    if current == 0 or legacy == 0 or historical_2020 == 0:
        raise RuntimeError(
            "Complete DataSF bundle is missing an inspection era: "
            f"current={current}, 2016-2019={legacy}, 2020-2023={historical_2020}"
        )
    if len(arsicault) < 4 or not any("397 ARGUELLO" in address for address in addresses):
        raise RuntimeError(f"Known complete-coverage regression failed for Arsicault Bakery: {arsicault}")
    if not snapshot.exists():
        raise RuntimeError("Leaderboard snapshot was not generated with the complete database")

    print(
        "Validated complete DataSF bundle: "
        f"source_counts={upstream_counts} normalized_rows={total} facilities={facilities} "
        f"current={current} legacy={legacy} historical_2020={historical_2020} "
        f"latest={result['latest_inspection_date']} arsicault_locations={len(arsicault)}",
        flush=True,
    )
