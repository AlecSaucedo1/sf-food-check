from app import add_consumer_risk
from backend.store import connect, restaurant_detail, upsert_inspections
from backend.taxonomy import parse_grouped_findings


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


def test_current_datasf_grouped_violation_format_parses_as_two_findings():
    items = parse_grouped_findings(HOUSE_OF_PRIME_RIB_VIOLATIONS)
    assert len(items) == 2
    assert items[0]["code"].startswith("114067(h), 114123")
    assert "vermin proof" in items[0]["official_description"]
    assert items[1]["code"].startswith("114143(d), 114266")
    assert "walls / ceilings" in items[1]["official_description"]


def _house_of_prime_rib_rows():
    violation_row = {
        "permit_number": "18531",
        "dba": "HOUSE OF PRIME RIB",
        "street_address": "1906 VAN NESS AVE",
        "inspection_date": "2026-08-13T00:00:00.000",
        "inspection_type": "Routine",
        "facility_rating_status": "Pass",
        "violation_count": "2",
        "violation_codes": HOUSE_OF_PRIME_RIB_VIOLATIONS,
    }
    summary_row = {
        "permit_number": "18531",
        "dba": "HOUSE OF PRIME RIB",
        "street_address": "1906 VAN NESS AVE",
        "inspection_date": "2026-08-13T00:00:00.000",
        "inspection_type": "Routine",
        "facility_rating_status": "Pass",
    }
    return violation_row, summary_row


def test_duplicate_summary_row_cannot_overwrite_violation_row():
    violation_row, summary_row = _house_of_prime_rib_rows()
    con = connect(":memory:")
    try:
        count = upsert_inspections(con, [violation_row, summary_row])
        assert count == 1
        stored = con.execute("SELECT violation_count, raw_json FROM inspections WHERE permit_number='18531'").fetchone()
        assert stored["violation_count"] == 2
        assert "vermin proof" in stored["raw_json"]

        detail = restaurant_detail(con, "18531")
        assert detail is not None
        assert len(detail["inspections"]) == 1
        assert len(detail["inspections"][0]["source_violations"]) == 2

        enriched = add_consumer_risk(detail)
        latest = enriched["inspections"][0]
        assert latest["display_violation_count"] == 2
        assert latest["mapping"]["mapped_count"] == 2
        assert latest["risk"]["risk_score"] > 0
        assert enriched["latest_risk"]["risk_score"] > 0
    finally:
        con.close()


def test_duplicate_merge_also_works_when_summary_row_arrives_first():
    violation_row, summary_row = _house_of_prime_rib_rows()
    con = connect(":memory:")
    try:
        count = upsert_inspections(con, [summary_row, violation_row])
        assert count == 1
        detail = add_consumer_risk(restaurant_detail(con, "18531"))
        assert detail["inspections"][0]["display_violation_count"] == 2
        assert len(detail["inspections"][0]["violations"]) == 2
    finally:
        con.close()


def test_house_of_prime_rib_preventive_and_structural_findings_are_not_treated_as_direct_hazards():
    violation_row, summary_row = _house_of_prime_rib_rows()
    con = connect(":memory:")
    try:
        upsert_inspections(con, [violation_row, summary_row])
        detail = add_consumer_risk(restaurant_detail(con, "18531"))
        latest = detail["inspections"][0]
        findings = latest["violations"]

        assert findings[0]["normalized_category"] == "Facility sanitation & pest prevention"
        assert findings[0]["risk_score"] == 55
        assert findings[0]["risk_level"] == "Elevated"

        assert findings[1]["normalized_category"] == "Facility condition & repair"
        assert findings[1]["risk_score"] == 35
        assert findings[1]["risk_level"] == "Moderate"

        assert latest["risk"]["risk_score"] == 59
        assert latest["risk"]["risk_level"] == "Elevated"
        assert latest["risk"]["risk_score"] < 75
    finally:
        con.close()
