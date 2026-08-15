from datetime import date

from backend.leaderboards import build_leaderboards, chain_identity
from backend.store import connect, upsert_inspections


def _row(permit, dba, address, neighborhood, *, violation_codes="", violation_count="0", status="Pass"):
    row = {
        "permit_number": permit,
        "dba": dba,
        "street_address": address,
        "analysis_neighborhood": neighborhood,
        "inspection_date": date.today().isoformat(),
        "inspection_type": "Routine",
        "facility_rating_status": status,
        "violation_count": violation_count,
    }
    if violation_codes:
        row["violation_codes"] = violation_codes
    return row


def test_chain_identity_removes_store_numbers_without_collapsing_generic_names():
    assert chain_identity("STARBUCKS COFFEE #1234") == ("STARBUCKS", "STARBUCKS")
    assert chain_identity("MCDONALD'S 1042") == ("MCDONALDS", "MCDONALD'S")
    assert chain_identity("CAFE") is None


def test_leaderboards_rank_lower_risk_first_and_require_minimum_samples():
    temp_violation = (
        "113996, 114343(a) - Potentially hazardous food shall be maintained at proper cold holding temperature."
    )
    rows = [
        _row("a1", "CLEAN CHAIN #101", "1 A ST", "Alpha"),
        _row("a2", "CLEAN CHAIN #102", "2 A ST", "Alpha"),
        _row("a3", "CLEAN CHAIN #103", "3 A ST", "Alpha"),
        _row("b1", "WARM CHAIN #201", "1 B ST", "Beta", violation_codes=temp_violation, violation_count="1"),
        _row("b2", "WARM CHAIN #202", "2 B ST", "Beta", violation_codes=temp_violation, violation_count="1"),
        _row("b3", "WARM CHAIN #203", "3 B ST", "Beta", violation_codes=temp_violation, violation_count="1"),
        _row("solo", "ONE LOCATION", "9 C ST", "Gamma"),
    ]

    con = connect(":memory:")
    try:
        upsert_inspections(con, rows)
        data = build_leaderboards(
            con,
            model_version="test",
            months=18,
            minimum_chain_locations=3,
            minimum_neighborhood_restaurants=3,
            limit=10,
        )
    finally:
        con.close()

    assert [item["name"] for item in data["chains"]] == ["CLEAN CHAIN", "WARM CHAIN"]
    assert data["chains"][0]["average_risk"] < data["chains"][1]["average_risk"]
    assert data["chains"][0]["location_count"] == 3
    assert [item["name"] for item in data["neighborhoods"]] == ["Alpha", "Beta"]
    assert data["methodology"]["direction"] == "lower_is_better"


def test_unmapped_cited_violations_are_excluded_from_comparative_rankings():
    rows = [
        _row("a1", "SAFE GROUP #1", "1 A ST", "Alpha"),
        _row("a2", "SAFE GROUP #2", "2 A ST", "Alpha"),
        _row("a3", "SAFE GROUP #3", "3 A ST", "Alpha"),
        _row("u1", "UNKNOWN GROUP #1", "1 U ST", "Unknownville", violation_codes="999999", violation_count="1"),
        _row("u2", "UNKNOWN GROUP #2", "2 U ST", "Unknownville", violation_codes="999999", violation_count="1"),
        _row("u3", "UNKNOWN GROUP #3", "3 U ST", "Unknownville", violation_codes="999999", violation_count="1"),
    ]

    con = connect(":memory:")
    try:
        upsert_inspections(con, rows)
        data = build_leaderboards(
            con,
            model_version="test-unmapped",
            months=18,
            minimum_chain_locations=3,
            minimum_neighborhood_restaurants=3,
            limit=10,
        )
    finally:
        con.close()

    assert [item["name"] for item in data["chains"]] == ["SAFE GROUP"]
    assert [item["name"] for item in data["neighborhoods"]] == ["Alpha"]
