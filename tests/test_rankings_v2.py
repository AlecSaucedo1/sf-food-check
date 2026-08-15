from datetime import date

from backend.rankings_v2 import build_leaderboards
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


def _rows():
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
    ]


def test_best_and_reverse_leaderboards_use_same_eligible_groups():
    con = connect(":memory:")
    try:
        upsert_inspections(con, _rows())
        data = build_leaderboards(
            con,
            months=18,
            minimum_chain_locations=3,
            minimum_neighborhood_restaurants=3,
            limit=10,
        )
    finally:
        con.close()

    assert [item["name"] for item in data["chains"]] == ["CLEAN CHAIN", "WARM CHAIN"]
    assert [item["name"] for item in data["highest_risk_chains"]] == ["WARM CHAIN", "CLEAN CHAIN"]
    assert [item["name"] for item in data["neighborhoods"]] == ["Alpha", "Beta"]
    assert [item["name"] for item in data["highest_risk_neighborhoods"]] == ["Beta", "Alpha"]
    assert data["methodology"]["direction"] == "lower_is_better"
    assert data["methodology"]["reverse_direction"] == "higher_is_worse"
    assert data["highest_risk_chains"][0]["average_risk"] < 100
