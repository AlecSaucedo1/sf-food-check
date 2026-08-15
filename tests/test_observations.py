from app import add_consumer_risk
from backend.observations import (
    assess_observation,
    attach_observations,
    codes_match,
    import_observations,
)
from backend.store import connect, restaurant_detail, upsert_inspections


REPORT = "https://inspections.myhealthdepartment.com/san-francisco/print/?task=getPrintable&path=san-francisco&pKey=TEST"


def test_observation_severity_uses_specific_condition_not_only_generic_violation():
    graded = assess_observation(
        "Inspector observed fresh rodent droppings on the food prep table adjacent to exposed food.",
        parent_score=55,
        parent_category="Facility sanitation & pest prevention",
    )
    assert graded["severity_score"] >= 90
    assert graded["severity_level"] == "Critical"
    assert graded["severity_confidence"] == "high"


def test_structural_observation_stays_moderate():
    graded = assess_observation(
        "A gap was observed beneath the rear door and the wall surface was damaged.",
        parent_score=55,
        parent_category="Facility sanitation & pest prevention",
    )
    assert graded["severity_score"] == 40
    assert graded["severity_level"] == "Moderate"


def test_grouped_codes_match_single_report_code():
    assert codes_match("114067(h), 114123, 114143(a, b)", "114123")
    assert codes_match("114067(h)", "114067")
    assert not codes_match("114067(h)", "114266")


def _row():
    return {
        "permit_number": "OBS1",
        "dba": "OBSERVATION TEST KITCHEN",
        "street_address": "1 TEST ST",
        "inspection_date": "2026-08-14T00:00:00.000",
        "inspection_type": "Routine",
        "facility_rating_status": "Pass",
        "violation_count": "1",
        "violation_codes": "114259 - Keep the premises free of vermin and pest activity.",
    }


def test_verified_observation_is_attached_to_violation_and_graded():
    con = connect(":memory:")
    try:
        upsert_inspections(con, [_row()])
        imported = import_observations(con, [{
            "permit_number": "OBS1",
            "inspection_date": "2026-08-14",
            "violation_code": "114259",
            "observation_text": "Inspector observed approximately 25 fresh mouse droppings on a food preparation table.",
            "corrective_action": "Clean and sanitize the affected food-contact surfaces and eliminate rodent activity.",
            "report_url": REPORT,
        }])
        assert imported == 1

        detail = restaurant_detail(con, "OBS1")
        assert detail is not None
        attach_observations(con, detail)
        enriched = add_consumer_risk(detail)
        inspection = enriched["inspections"][0]
        assert inspection["observation_mapping"]["matched_count"] == 1
        assert inspection["observation_mapping"]["unmatched_count"] == 0
        observation = inspection["violations"][0]["observations"][0]
        assert observation["observation_text"].startswith("Inspector observed")
        assert observation["severity_score"] >= 90
        assert observation["severity_level"] == "Critical"
        assert observation["report_url"] == REPORT
        assert inspection["report"]["report_url"] == REPORT
    finally:
        con.close()


def test_unmatched_observation_is_preserved_instead_of_guessed():
    con = connect(":memory:")
    try:
        upsert_inspections(con, [_row()])
        import_observations(con, [{
            "permit_number": "OBS1",
            "inspection_date": "2026-08-14",
            "violation_code": "999999",
            "observation_text": "Inspector observed a separate condition that cannot be matched to the published code.",
            "report_url": REPORT,
        }])
        detail = restaurant_detail(con, "OBS1")
        attach_observations(con, detail)
        enriched = add_consumer_risk(detail)
        inspection = enriched["inspections"][0]
        assert inspection["observation_mapping"]["matched_count"] == 0
        assert inspection["observation_mapping"]["unmatched_count"] == 1
        assert len(inspection["unmatched_observations"]) == 1
        assert not inspection["violations"][0].get("observations")
    finally:
        con.close()
