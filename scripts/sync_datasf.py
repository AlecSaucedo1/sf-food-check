#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.sync_service import sync_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Atomically sync the current SFDPH inspection dataset from DataSF into SQLite.")
    parser.add_argument("--db", default=os.getenv("DATABASE_PATH", str(ROOT / "data" / "inspections.db")))
    parser.add_argument("--page-size", type=int, default=5000)
    parser.add_argument("--max-rows", type=int, default=100000)
    parser.add_argument("--save-raw", default="", help="Optional path to save a raw JSON snapshot.")
    parser.add_argument("--reset", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    result = asyncio.run(sync_once(args.db, page_size=args.page_size, max_rows=args.max_rows, save_raw=args.save_raw))
    print(f"Imported {result['rows']:,} inspection rows; database now contains {result['facilities']:,} facilities. Latest inspection: {result['latest_inspection_date']}.")


if __name__ == "__main__":
    main()
