from datetime import date
from pathlib import Path

from backend.leaderboards import (
    build_leaderboards,
    chain_identity,
    leaderboard_snapshot_path,
    parse_datasf_findings,
    refresh_leaderboard_snapshot,
)
from backend.store import connect, upsert_inspections


HOUSE_OF_PRIME_RIB_VIOLATIONS = (
    "114067(h), 114123, 114143(a, b), 114256-114256.2, 114256.4, "
    "114257-114257.1, 114259, 114259.2-114259.3, 114279, 114281, 114282 - "
    "Keep clean and free of litter or rubbish the premises of each food facility; "
    "non-food items shall be stored and displayed separate from food and food-contact surfaces; "
    "the facility shall be kept vermin proof; open-air barbecues shall be operated in an approved manner., "
    "114143(d), 114266, 114268, 114268.1, 114271, 114272 - "
    "Provide walls / ceilings using materials that are durable, smooth, nonabsorbent, light-colored, "
    "and washable surfaces. All floor surfaces, other than the customer service areas, shall be approved, "
    "smooth, durable, and made of nonabsorbent material that is easily cleanable. Approved base coving "
    "shall be provided in all areas, except customer service areas and where food is stored in original "
    "unopened containers. Food facilities shall be fully enclosed. All food facilities shall be kept clean "
    "and in good repair."
)


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


def test_fast_datasf_parser_preserves_grouped_codes_and_descriptions():
    findings = parse_datasf_findings(HOUSE_OF_PRIME_RIB_VIOLATIONS)
    assert len(findings) == 2
    assert findings[0]["code"].startswith("114067(h), 114123")
    assert "vermin proof" in findings[0]["official_description"]
    assert findings[1]["code"].startswith("114143(d), 114266")
    assert "walls / ceilings" in findings[1]["official_description"]


def _sample_rows():
    temp_violation = (
        "113996, 114343(a) - Potentially hazardous food shall be maintained at proper cold holding temperature."
    )
    return [
        _row("a1", "CLEAN CHAIN #101", "1 A ST", "Alpha"),
        _row("a2", "CLEAN CHAIN #102", "2 A ST", "Alpha"),
        _row("a3", "CLEAN CHAIN #103", "3 A ST", "Alpha"),
        _row("b1", "WARM CHAIN #201", "1 B ST", "Beta", violation_codes=temp_violation, violation_count="1"),
        _row("b2", "WARM CHAIN #202", "2 B ST", "Beta", violation_codes=temp_violation, violation_count="1"),
        _row("b3", "WARM CHAIN #203", "3 B ST", "Beta", violation_codes=temp_violation, violation_count="1"),
        _row("solo", "ONE LOCATION", "9 C ST", "Gamma"),
    ]


def test_leaderboards_rank_lower_risk_first_and_require_minimum_samples():
    con = connect(":memory:")
    try:
        upsert_inspections(con, _sample_rows())
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


def test_materialized_snapshot_serves_rankings_without_rescoring_request(tmp_path):
    db_path = str(tmp_path / "inspections.db")
    with connect(db_path) as con:
        upsert_inspections(con, _sample_rows())

    snapshot = refresh_leaderboard_snapshot(db_path, model_version="snapshot-test")
    snapshot_path = leaderboard_snapshot_path(db_path)
    assert snapshot["facility_count"] == 7
    assert Path(snapshot_path).exists()

    with connect(db_path) as con:
        con.execute("DELETE FROM inspections")
        con.commit()
        data = build_leaderboards(
            con,
            model_version="snapshot-test",
            months=18,
            minimum_chain_locations=3,
            minimum_neighborhood_restaurants=3,
            limit=10,
            snapshot_path=snapshot_path,
        )

    assert [item["name"] for item in data["chains"]] == ["CLEAN CHAIN", "WARM CHAIN"]
    assert data["methodology"]["snapshot_generated_at"]
    assert data["methodology"]["eligible_facilities"] == 7


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
