from backend.taxonomy import (
    assess_inspection,
    assess_violation,
    extract_source_violations,
    parse_violation,
)


def test_parse_violation_with_code_and_text():
    assert parse_violation("103103: High risk food holding temperature") == ("103103", "High risk food holding temperature")


def test_temperature_is_high_risk():
    v = assess_violation("Improper cold holding temperature")
    assert v["normalized_category"] == "Temperature control"
    assert v["risk_score"] >= 75


def test_admin_issue_is_low_risk():
    v = assess_violation("Food safety manager certificate unavailable")
    assert v["risk_score"] <= 20


def test_multiple_findings_raise_inspection_index():
    a = assess_violation("Improper cold holding temperature")
    b = assess_violation("Food-contact surface not sanitized")
    result = assess_inspection([a, b], status="Pass", violation_count=2)
    assert result["risk_score"] > a["risk_score"]
    assert result["risk_score"] <= 100


def test_conditional_pass_has_major_violation_floor():
    result = assess_inspection([], status="Conditional Pass", violation_count=2)
    assert result["risk_score"] >= 80


def test_extracts_paired_code_and_description_fields():
    raw = {
        "violation_codes": "103103, 103119",
        "violation_descriptions": "Improper cold holding temperature | Inadequate hand washing facilities",
    }
    items = extract_source_violations(raw)
    assert len(items) == 2
    assert items[0]["code"] == "103103"
    assert "cold holding" in items[0]["official_description"].lower()
    assert items[1]["code"] == "103119"
    assert "hand washing" in items[1]["official_description"].lower()


def test_extracts_combined_violation_entries():
    raw = {
        "violations": "103103: Improper cold holding temperature; 103119: Inadequate hand washing facilities"
    }
    items = extract_source_violations(raw)
    assert [(x["code"], x["official_description"]) for x in items] == [
        ("103103", "Improper cold holding temperature"),
        ("103119", "Inadequate hand washing facilities"),
    ]


def test_extracts_serialized_json_arrays_and_deduplicates_fallback():
    raw = {
        "violation_codes": '["103103", "103119"]',
        "violation_descriptions": '["Improper cold holding temperature", "Inadequate hand washing facilities"]',
    }
    items = extract_source_violations(raw, ["103103", "103119"])
    assert len(items) == 2
    assert all(item["official_description"] for item in items)


def test_code_only_is_labeled_as_limited_detail_not_guessed():
    item = assess_violation("103103")
    assert item["normalized_category"] == "Official violation code"
    assert item["risk_confidence"] == "low"
    assert item["official_description"] is None


def test_official_high_risk_category_sets_conservative_floor():
    item = assess_violation(
        "Other published finding",
        official_description="Other published finding",
        official_risk_category="High Risk",
    )
    assert item["risk_score"] >= 80
    assert item["risk_level"] == "High"
