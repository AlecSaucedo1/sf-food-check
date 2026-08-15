import os
import subprocess
import sys
from pathlib import Path

from backend.store import connect, list_restaurants


def test_external_complete_bundle_build(tmp_path):
    output = tmp_path / "complete-inspections.db"
    env = dict(os.environ)
    env["BUNDLED_DATABASE_PATH"] = str(output)
    subprocess.run([sys.executable, "scripts/build_complete_bundle.py"], check=True, env=env, timeout=180)

    assert output.exists()
    assert output.with_name("leaderboard_facilities.json").exists()
    with connect(str(output)) as con:
        rows = list_restaurants(con, q="Arsicault", limit=200)
        assert len(rows) >= 4
        assert any("397 ARGUELLO" in " ".join(str(row.get("street_address") or "").upper().split()) for row in rows)
