from backend.store import connect, list_restaurants, nearby, upsert_inspections
from backend.normalize import normalize_row


def test_latest_facility_materialized_and_status_applies_to_latest_only(tmp_path):
    with connect(str(tmp_path / "facilities.db")) as con:
        upsert_inspections(con, [
            {"permit_number": "1", "dba": "Old Name", "street_address": "1 Market St", "inspection_date": "2024-01-01", "facility_rating_status": "Pass"},
            {"permit_number": "1", "dba": "New Name", "street_address": "1 Market St", "inspection_date": "2026-08-01", "facility_rating_status": "Conditional Pass"},
            {"permit_number": "2", "dba": "Other Cafe", "street_address": "2 Market St", "inspection_date": "2026-07-01", "facility_rating_status": "Pass"},
        ])
        rows = con.execute("SELECT permit_number FROM facility_latest").fetchall()
        assert {x["permit_number"] for x in rows} == {"1", "2"}
        assert [r["dba"] for r in list_restaurants(con, q="New Name")] == ["New Name"]
        assert not list_restaurants(con, q="Old Name")
        assert [r["permit_number"] for r in list_restaurants(con, status="Pass")] == ["2"]
        assert [r["permit_number"] for r in list_restaurants(con, q="Market St", limit=200)] == ["1", "2"]


def test_nearby_search_considers_all_facilities_not_only_latest_two_hundred(tmp_path):
    rows = [
        {
            "permit_number": str(i),
            "dba": f"Far Restaurant {i}",
            "street_address": f"{i} Far St",
            "inspection_date": "2026-10-01",
            "facility_rating_status": "Pass",
            "latitude": 40.0, "longitude": -120.0,
        }
        for i in range(210)
    ]
    rows.append({
        "permit_number": "local",
        "dba": "Neighborhood Restaurant",
        "street_address": "100 Local St",
        "inspection_date": "2019-01-01",
        "facility_rating_status": "Historical",
        "latitude": 37.775, "longitude": -122.419,
    })
    with connect(str(tmp_path / "nearby.db")) as con:
        upsert_inspections(con, rows)
        items = nearby(con, 37.775, -122.419, radius_km=2.0)
    assert len(items) == 1
    assert items[0]["permit_number"] == "local"
    assert items[0]["distance_km"] == 0.0


def test_facility_latest_rebuilds_after_bulk_replace(tmp_path):
    from backend.store import replace_inspections
    with connect(str(tmp_path / "replace.db")) as con:
        upsert_inspections(con, [{"permit_number": "old", "dba": "Old", "inspection_date": "2025-01-01"}])
        replace_inspections(con, [{"permit_number": "new", "dba": "New", "inspection_date": "2026-08-01"}])
        assert [r["dba"] for r in list_restaurants(con)] == ["New"]
        assert con.execute("SELECT COUNT(*) FROM facility_latest").fetchone()[0] == 1
