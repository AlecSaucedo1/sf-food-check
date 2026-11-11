"""Temporary pre-deployment full-data integration test; remove after it passes."""
from datetime import date
import os
import subprocess
import sys
from backend.store import connect, list_restaurants

def test_live_three_era_build_and_current_dataset(tmp_path):
    out = tmp_path / "complete-inspections.db"
    env = {**os.environ, "BUNDLED_DATABASE_PATH": str(out)}
    subprocess.run([sys.executable, "scripts/build_complete_bundle.py"], env=env, check=True, timeout=240)
    with connect(str(out)) as con:
        total = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
        latest = con.execute("SELECT MAX(inspection_date) FROM inspections").fetchone()[0]
        indexed = con.execute("SELECT COUNT(*) FROM facility_latest").fetchone()[0]
        physical = len(list_restaurants(con, q="Arsicault", limit=200))
    print("FULL_BUILD", {"rows":total,"latest":latest,"indexed":indexed,"Arsicault":physical})
    assert total > 65000
    assert indexed > 13000
    assert latest >= "2026-10-01"
    assert latest <= date.today().isoformat()
    assert physical == 4
