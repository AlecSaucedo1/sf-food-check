#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.store import connect
from backend.taxonomy import categorize


def main():
    p = argparse.ArgumentParser(description="Attach violation descriptions/taxonomy to normalized inspections.")
    p.add_argument("file", help="CSV columns: inspection_id, code, official_description, risk_level, inspector_comment")
    p.add_argument("--db", default=os.getenv("DATABASE_PATH", str(ROOT / "data" / "inspections.db")))
    args = p.parse_args()
    with Path(args.file).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    with connect(args.db) as con:
        for r in rows:
            interpretation = categorize(r.get("official_description"))
            con.execute("""INSERT INTO violations
                (inspection_id, code, official_description, normalized_category, consumer_description, risk_level, inspector_comment)
                VALUES (?,?,?,?,?,?,?)""",(
                r.get("inspection_id"), r.get("code"), r.get("official_description"),
                r.get("normalized_category") or interpretation["normalized_category"],
                r.get("consumer_description") or interpretation["consumer_description"],
                r.get("risk_level"), r.get("inspector_comment")
            ))
        con.commit()
    print(f"Imported {len(rows)} violation detail row(s).")

if __name__ == "__main__":
    main()
