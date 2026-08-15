from backend.data_coverage import _aggregate_2020, _aggregate_legacy, _reconcile_with_current
from backend.store import connect, list_restaurants, upsert_inspections


def test_aggregate_2020_groups_multiple_findings_into_one_inspection():
    rows = [
        {
            "name": "Example Bakery",
            "address": "1 MAIN ST",
            "inspection_id": "abc",
            "date": "2023-06-01T00:00:00.000",
            "facility_status": "PASS",
            "inspection_type": "routine",
            "violation_observed": "OUT (Not in Compliance)",
            "description": "Improper cold holding",
        },
        {
            "name": "Example Bakery",
            "address": "1 MAIN ST",
            "inspection_id": "abc",
            "date": "2023-06-01T00:00:00.000",
            "facility_status": "PASS",
            "inspection_type": "routine",
            "violation_observed": "Minor",
            "description": "Floors not clean",
        },
    ]
    result = _aggregate_2020(rows)
    assert len(result) == 1
    assert result[0]["inspection_id"] == "H20:abc"
    assert result[0]["violation_count"] == 2
    assert len(result[0]["violation_codes"]) == 2


def test_aggregate_legacy_preserves_arsicault_arguello_identity_and_findings():
    rows = [
        {
            "business_id": "81264",
            "business_name": "Arsicault Bakery",
            "business_address": "397 Arguello Blvd",
            "inspection_id": "81264_20170103",
            "inspection_date": "2017-01-03T00:00:00.000",
            "inspection_score": "96",
            "inspection_type": "Routine - Unscheduled",
            "violation_id": "81264_20170103_103154",
            "violation_description": "Unclean or degraded floors walls or ceilings",
            "risk_category": "Low Risk",
        },
        {
            "business_id": "81264",
            "business_name": "Arsicault Bakery",
            "business_address": "397 Arguello Blvd",
            "inspection_id": "81264_20170103",
            "inspection_date": "2017-01-03T00:00:00.000",
            "inspection_score": "96",
            "inspection_type": "Routine - Unscheduled",
            "violation_id": "81264_20170103_103161",
            "violation_description": "Low risk vermin infestation",
            "risk_category": "Low Risk",
        },
    ]
    result = _aggregate_legacy(rows)
    assert len(result) == 1
    assert result[0]["permit_number"] == "H16-81264"
    assert result[0]["street_address"] == "397 Arguello Blvd"
    assert result[0]["violation_count"] == 2
    assert result[0]["facility_rating_status"] == "Historical"


def test_historical_rows_reconcile_to_current_permit_only_at_same_name_and_address():
    current = [{
        "permit_number": "102298",
        "dba": "ARSICAULT BAKERY",
        "street_address": "87 MCALLISTER ST",
        "street_address_clean": "87 MCALLISTER ST",
        "analysis_neighborhood": "Tenderloin",
    }]
    historical = [
        {"permit_number": "H20-one", "dba": "Arsicault Bakery", "street_address": "87 McAllister St"},
        {"permit_number": "H16-81264", "dba": "Arsicault Bakery", "street_address": "397 Arguello Blvd"},
    ]
    result = _reconcile_with_current(current, historical)
    assert result[0]["permit_number"] == "102298"
    assert result[0]["analysis_neighborhood"] == "Tenderloin"
    assert result[1]["permit_number"] == "H16-81264"


def test_search_returns_four_arsicault_facilities_when_historical_arguello_is_loaded(tmp_path):
    current = [
        {"permit_number": "06733269", "dba": "Arsicault Bakery", "street_address": "1070 Bridgeview Way Unit B", "inspection_date": "2026-07-09", "facility_rating_status": "Pass"},
        {"permit_number": "102298", "dba": "Arsicault Bakery", "street_address": "87 McAllister St", "inspection_date": "2026-03-13", "facility_rating_status": "Pass"},
        {"permit_number": "06734504", "dba": "Arsicault Bakery", "street_address": "2565 3rd St Ste 202", "inspection_date": "2026-02-27", "facility_rating_status": "Pass"},
    ]
    legacy = _aggregate_legacy([{
        "business_id": "81264",
        "business_name": "Arsicault Bakery",
        "business_address": "397 Arguello Blvd",
        "business_city": "San Francisco",
        "business_state": "CA",
        "business_postal_code": "94118",
        "inspection_id": "81264_20190722",
        "inspection_date": "2019-07-22T00:00:00.000",
        "inspection_score": "100",
        "inspection_type": "Routine - Unscheduled",
    }])
    rows = current + legacy
    db_path = str(tmp_path / "coverage.db")
    with connect(db_path) as con:
        upsert_inspections(con, rows)
        results = list_restaurants(con, q="Arsicault", limit=200)
    assert len(results) == 4
    assert {item["street_address"] for item in results} == {
        "1070 Bridgeview Way Unit B",
        "87 McAllister St",
        "2565 3rd St Ste 202",
        "397 Arguello Blvd",
    }
