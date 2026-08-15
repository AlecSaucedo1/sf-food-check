import os
import subprocess
import sys

from backend.store import connect, list_restaurants


def test_external_bundle_has_four_deduplicated_arsicault_locations(tmp_path):
    output = tmp_path / "complete-inspections.db"
    env = dict(os.environ)
    env["BUNDLED_DATABASE_PATH"] = str(output)
    subprocess.run([sys.executable, "scripts/build_complete_bundle.py"], check=True, env=env, timeout=180)
    with connect(str(output)) as con:
        rows = list_restaurants(con, q="Arsicault", limit=200)
        assert len(rows) == 4
        arguello = [r for r in rows if "397 ARGUELLO" in " ".join(str(r.get("street_address") or "").upper().split())]
        assert len(arguello) == 1
        history = con.execute(
            "SELECT inspection_date, facility_rating_status FROM inspections WHERE permit_number=? ORDER BY inspection_date DESC",
            (arguello[0]["permit_number"],),
        ).fetchall()
        assert any(str(row[0]).startswith("2023-") for row in history)
        assert any(str(row[0]).startswith("2019-") for row in history)
