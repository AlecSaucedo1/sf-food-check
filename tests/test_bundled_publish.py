import json
from pathlib import Path

from backend.observations import ensure_observation_schema
from backend.store import connect, import_enrichment, list_restaurants, upsert_inspections
import scripts.publish_bundled_db as publisher


def _rows():
    return [
        {"permit_number": "1", "dba": "Arsicault Bakery", "street_address": "397 Arguello Blvd", "inspection_date": "2019-07-22", "facility_rating_status": "Historical"},
        {"permit_number": "2", "dba": "Arsicault Bakery", "street_address": "87 McAllister St", "inspection_date": "2026-03-13", "facility_rating_status": "Pass"},
        {"permit_number": "3", "dba": "Arsicault Bakery", "street_address": "1070 Bridgeview Way Unit B", "inspection_date": "2026-07-09", "facility_rating_status": "Pass"},
        {"permit_number": "4", "dba": "Arsicault Bakery", "street_address": "2565 3rd St Ste 202", "inspection_date": "2026-02-27", "facility_rating_status": "Pass"},
    ]


def test_publish_bundle_preserves_enrichment_and_switches_active_symlink(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle.db"
    snapshot = tmp_path / "leaderboard_facilities.json"
    previous = tmp_path / "previous.db"
    active = tmp_path / "active.db"
    live_snapshot = tmp_path / "live-leaderboard.json"

    with connect(str(bundle)) as con:
        upsert_inspections(con, _rows())
    snapshot.write_text(json.dumps({"model_version": "test", "facilities": []}), encoding="utf-8")

    with connect(str(previous)) as con:
        upsert_inspections(con, [_rows()[1]])
        import_enrichment(con, [{
            "permit_number": "2",
            "inspection_date": "2026-03-13",
            "report_url": "https://example.test/report",
            "inspector_comments": "Official inspector comment",
            "corrective_action": "Corrected",
            "source_label": "Official report",
        }])
        ensure_observation_schema(con)
        inspection_id = con.execute("SELECT inspection_id FROM inspections WHERE permit_number='2'").fetchone()[0]
        con.execute(
            """INSERT INTO violation_observations
            (inspection_id, permit_number, inspection_date, violation_code, observation_text, report_url)
            VALUES (?,?,?,?,?,?)""",
            (inspection_id, "2", "2026-03-13", "114259", "Observed pest activity", "https://example.test/report"),
        )
        con.commit()

    active.symlink_to(previous.name)

    monkeypatch.setattr(publisher, "BUNDLE_DB", bundle)
    monkeypatch.setattr(publisher, "BUNDLE_SNAPSHOT", snapshot)
    monkeypatch.setattr(publisher, "ACTIVE_DB", active)
    monkeypatch.setattr(publisher, "LEGACY_DB", previous)
    monkeypatch.setattr(publisher, "LIVE_SNAPSHOT", live_snapshot)

    publisher.main()

    assert active.is_symlink()
    assert Path(active.resolve()).name.startswith("inspections-bundle-")
    assert live_snapshot.exists()

    with connect(str(active)) as con:
        restaurants = list_restaurants(con, q="Arsicault", limit=200)
        assert len(restaurants) == 4
        enrichment = con.execute(
            "SELECT inspector_comments FROM report_enrichment WHERE permit_number='2' AND inspection_date='2026-03-13'"
        ).fetchone()
        assert enrichment[0] == "Official inspector comment"
        observations = con.execute("SELECT COUNT(*) FROM violation_observations").fetchone()[0]
        assert observations == 1
