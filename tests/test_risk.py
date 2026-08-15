from backend.taxonomy import assess_inspection, assess_violation, parse_violation


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
