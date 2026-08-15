from backend.scoring_v2 import assess_inspection, assess_violation, calibrate_score


def test_common_high_risk_finding_no_longer_sits_near_ceiling():
    item = assess_violation("Improper cold holding temperature")
    assert 65 <= item["risk_score"] <= 75
    assert item["risk_level"] == "High"


def test_generic_critical_finding_is_serious_without_being_100():
    item = assess_violation("Sick employee with diarrhea handled food")
    assert 88 <= item["risk_score"] <= 92
    assert item["risk_level"] == "Critical"


def test_multiple_serious_findings_use_diminishing_returns():
    critical = assess_violation("Sick employee with diarrhea handled food")
    high = assess_violation("Improper cold holding temperature")
    result = assess_inspection([critical, high, high], status="Pass", violation_count=3)
    assert result["risk_score"] > critical["risk_score"]
    assert result["risk_score"] < 98
    assert result["risk_score"] < 100


def test_even_many_high_findings_do_not_saturate_at_100():
    high = assess_violation("Improper cold holding temperature")
    result = assess_inspection([high] * 8, status="Pass", violation_count=8)
    assert result["risk_score"] <= 98


def test_status_floors_signal_seriousness_without_forcing_near_perfect_scores():
    conditional = assess_inspection([], status="Conditional Pass", violation_count=2)
    closure = assess_inspection([], status="Closure", violation_count=1)
    assert conditional["risk_score"] == 70
    assert closure["risk_score"] == 92


def test_legacy_100_is_recalibrated_below_ceiling():
    assert calibrate_score(100) == 96
    assert calibrate_score(80) < 80
    assert calibrate_score(35) < 35
