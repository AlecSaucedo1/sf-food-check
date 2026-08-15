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
from backend.store import connect, import_enrichment

REQUIRED = {"permit_number", "inspection_date"}


def load(path: Path):
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text())
        return value if isinstance(value, list) else value.get("enrichment", [])
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    p = argparse.ArgumentParser(description="Import verified inspector comments / official report links.")
    p.add_argument("file", help="CSV or JSON with permit_number, inspection_date, report_url, inspector_comments, corrective_action.")
    p.add_argument("--db", default=os.getenv("DATABASE_PATH", str(ROOT / "data" / "inspections.db")))
    args = p.parse_args()
    items = load(Path(args.file))
    for i, item in enumerate(items, 1):
        missing = [k for k in REQUIRED if not item.get(k)]
        if missing:
            raise SystemExit(f"Row {i} missing required field(s): {', '.join(missing)}")
        item.setdefault("comment_source", "manual_official")
        item.setdefault("source_label", "Official SFDPH inspection report")
    with connect(args.db) as con:
        n = import_enrichment(con, items)
    print(f"Imported {n} report-enrichment record(s).")


if __name__ == "__main__":
    main()
