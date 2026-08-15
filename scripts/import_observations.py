#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.observations import import_observations
from backend.store import connect


def load(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            return value
        return value.get("observations", [])
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import verified violation-level observations from official SFDPH inspection reports."
    )
    parser.add_argument(
        "file",
        help=(
            "CSV or JSON containing permit_number, inspection_date, violation_code, "
            "observation_text, corrective_action, and report_url."
        ),
    )
    parser.add_argument(
        "--db",
        default=os.getenv("DATABASE_PATH", str(ROOT / "data" / "inspections.db")),
    )
    args = parser.parse_args()

    items = load(Path(args.file))
    if not items:
        raise SystemExit("No observation records found in the input file.")

    for index, item in enumerate(items, 1):
        if not (item.get("inspection_id") or (item.get("permit_number") and item.get("inspection_date"))):
            raise SystemExit(f"Row {index} must include inspection_id or permit_number + inspection_date.")
        if not (item.get("observation_text") or item.get("observation") or item.get("inspector_observation")):
            raise SystemExit(f"Row {index} is missing observation_text.")
        if not item.get("report_url"):
            raise SystemExit(f"Row {index} is missing report_url; official-report provenance is required.")
        item.setdefault("source_label", "Official SFDPH inspection report")

    with connect(args.db) as con:
        try:
            imported = import_observations(con, items)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    print(f"Imported {imported} verified observation record(s).")


if __name__ == "__main__":
    main()
