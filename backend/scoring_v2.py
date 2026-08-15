from __future__ import annotations

import math
from typing import Any

from .taxonomy import assess_inspection as _legacy_assess_inspection
from .taxonomy import assess_violation as _legacy_assess_violation

RISK_MODEL_VERSION = "2026.08.15.4"


def risk_band(score: int) -> str:
    """Consumer-facing bands for the recalibrated 0-100 index."""
    if score >= 90:
        return "Critical"
    if score >= 70:
        return "High"
    if score >= 45:
        return "Elevated"
    if score >= 20:
        return "Moderate"
    if score > 0:
        return "Low"
    return "No cited risk"


def calibrate_score(score: int | float | None) -> int:
    """Spread legacy severity values across the scale and reserve the top end.

    The original model used 80/95 as common finding scores, which made inspection
    totals saturate at 100 after only one or two additional findings. This curve
    preserves rank/order while making 90+ genuinely exceptional. Individual
    findings top out at 96; an inspection aggregate tops out at 98.
    """
    value = max(0.0, min(100.0, float(score or 0)))
    if value == 0:
        return 0
    return min(96, round(96 * (value / 100.0) ** 1.22))


def calibrate_violation_item(item: dict[str, Any]) -> dict[str, Any]:
    calibrated = dict(item)
    score = calibrate_score(item.get("risk_score"))
    calibrated["risk_score"] = score
    if not item.get("official_description") and item.get("risk_confidence") == "low":
        calibrated["risk_level"] = "Limited detail"
    else:
        calibrated["risk_level"] = risk_band(score)
    return calibrated


def assess_violation(*args, **kwargs) -> dict[str, Any]:
    return calibrate_violation_item(_legacy_assess_violation(*args, **kwargs))


def assess_inspection(
    violations: list[dict[str, Any]],
    *,
    status: str = "",
    violation_count: int = 0,
) -> dict[str, Any]:
    """Aggregate finding severity with diminishing returns instead of linear stacking.

    The most serious finding remains the anchor. Additional findings can raise the
    inspection score, but they fill only part of the remaining headroom. This keeps
    100 from becoming a routine result while still distinguishing repeated serious
    deficiencies from an isolated finding.
    """
    base = _legacy_assess_inspection(violations, status=status, violation_count=violation_count)
    scores = sorted(
        [int(v.get("risk_score") or 0) for v in violations if v.get("risk_score") is not None],
        reverse=True,
    )

    if scores:
        top = scores[0]
        additional = sum(scores[1:])
        headroom = max(0, 98 - top)
        bonus = round(headroom * (1 - math.exp(-additional / 180.0))) if additional else 0
        score = min(98, top + bonus)
    elif violation_count:
        # Missing descriptions should not masquerade as extreme risk.
        score = min(45, 18 + max(0, int(violation_count) - 1) * 5)
    else:
        score = 0

    status_norm = str(status or "").strip().lower()
    if "closure" in status_norm or "closed" in status_norm:
        # Closure remains an exceptionally serious signal, but is not automatically 100.
        score = max(score, 92)
    elif "conditional" in status_norm:
        # Conditional Pass raises the floor without overwhelming the actual findings.
        score = max(score, 70)

    base.update(
        risk_score=score,
        risk_level=risk_band(score),
        methodology=(
            "Recalibrated relative foodborne-illness risk index. The most serious finding anchors the score; "
            "additional findings contribute with diminishing returns. 100 is intentionally reserved and is not "
            "a probability or an official SFDPH score."
        ),
        model_version=RISK_MODEL_VERSION,
    )
    return base
