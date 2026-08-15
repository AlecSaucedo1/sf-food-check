from __future__ import annotations

import re
from typing import Any

CATEGORY_RULES = [
    (["ill employee", "sick employee", "employee illness", "vomit", "diarrhea"], "Employee illness", "A sick-food-worker control was not met, creating a direct contamination risk."),
    (["bare hand", "bare-hand", "ready-to-eat", "cross contamination", "cross-contamination"], "Cross-contamination", "Food handling could transfer pathogens to ready-to-eat food."),
    (["cook", "undercook", "reheat", "pasteur", "parasite destruction"], "Cooking & reheating", "Food did not fully meet a required pathogen-kill step such as cooking, reheating, or parasite destruction."),
    (["cold hold", "hot hold", "temperature", "cooling", "refriger", "time as a public health control"], "Temperature control", "Food was not kept within time or temperature controls intended to prevent pathogen growth."),
    (["unsafe source", "unapproved source", "approved source", "shellstock", "shellfish tag", "adulterat"], "Food source & contamination", "Food source, traceability, or contamination controls did not meet safety requirements."),
    (["handwash", "hand wash", "hand washing", "soap", "paper towel"], "Hand washing", "A handwashing facility or required handwashing practice did not meet requirements."),
    (["sanitize", "sanitiz", "food-contact", "food contact", "utensil"], "Food-contact sanitation", "A food-contact surface, utensil, or sanitizing process did not meet requirements."),
    (["vermin", "rodent", "cockroach", "pest", "insect", "flies", "fly"], "Pests", "Inspectors observed pests or a condition that could allow pest contamination."),
    (["sewage", "wastewater", "potable water", "water supply"], "Water & sewage", "A water or sewage condition could directly affect food safety."),
    (["thaw", "storage", "stored", "covered", "container", "protected from contamination"], "Food storage & protection", "Food storage or protection practices did not fully prevent contamination or unsafe handling."),
    (["plumb", "sink", "drain"], "Plumbing & sinks", "A sink, drain, or plumbing requirement was not met."),
    (["clean", "floor", "wall", "ceiling", "equipment", "repair", "maintain", "garbage", "refuse", "ventilation"], "Facility cleanliness & maintenance", "A cleaning, maintenance, refuse, ventilation, or facility-condition requirement was not met."),
    (["certificate", "manager", "procedure", "haccp", "plan", "permit", "documentation", "label", "signage"], "Food-safety procedures", "A required food-safety procedure, credential, label, permit, or record was missing or incomplete."),
    (["employee", "personal", "glove", "hair"], "Employee practices", "An employee food-safety practice did not meet requirements."),
]

SEVERITY_RULES = [
    (95, "Critical", ["ill employee", "sick employee", "employee illness", "vomit", "diarrhea", "sewage", "wastewater overflow", "unsafe source", "unapproved source", "adulterat", "cross contamination", "cross-contamination", "bare hand", "undercook", "inadequate cooking", "improper cooking", "inadequate reheating", "parasite destruction"], "Direct pathway for pathogens to contaminate food or survive a required kill step."),
    (80, "High", ["cold hold", "hot hold", "temperature", "cooling", "refriger", "handwash", "hand wash", "hand washing", "sanitize", "sanitiz", "food-contact", "food contact", "vermin", "rodent", "cockroach", "pest", "shellstock", "shellfish tag", "potable water", "water supply"], "Strongly associated with contamination or pathogen growth when uncontrolled."),
    (60, "Elevated", ["thaw", "protected from contamination", "food storage", "stored", "covered", "wiping cloth", "utensil", "glove", "plumb", "sink", "drain"], "Can meaningfully increase foodborne-illness risk, depending on the specific condition."),
    (35, "Moderate", ["clean", "equipment", "garbage", "refuse", "repair", "maintain", "floor", "wall", "ceiling", "ventilation", "employee practice"], "Primarily a sanitation or operational control issue with a less direct illness pathway."),
    (15, "Low", ["certificate", "manager", "permit", "documentation", "label", "signage", "hair", "lighting", "procedure", "plan"], "Mostly administrative, documentation, or lower-immediacy food-safety concern."),
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def parse_violation(raw: str | None) -> tuple[str, str]:
    value = _text(raw)
    if not value:
        return "", ""
    m = re.match(r"^\s*(\d{2,6})\s*[:\-–—|]\s*(.+)$", value)
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(r"^\s*(\d{5,6})\s+(.+)$", value)
    if m:
        return m.group(1), m.group(2).strip()
    if re.fullmatch(r"\d{2,6}", value):
        return value, ""
    return "", value


def categorize(official_description: str | None) -> dict[str, str | None]:
    text = _text(official_description).lower()
    for words, category, consumer in CATEGORY_RULES:
        if any(w in text for w in words):
            return {"normalized_category": category, "consumer_description": consumer}
    return {"normalized_category": "Other food-safety requirement", "consumer_description": "The inspection cited a food-safety requirement that does not map cleanly to a consumer category."}


def severity(official_description: str | None) -> dict[str, Any]:
    text = _text(official_description).lower()
    for score, level, words, rationale in SEVERITY_RULES:
        if any(w in text for w in words):
            return {"risk_score": score, "risk_level": level, "risk_rationale": rationale, "risk_confidence": "high"}
    if text:
        return {"risk_score": 30, "risk_level": "Moderate", "risk_rationale": "The finding is relevant to food safety, but its direct connection to foodborne illness is not clear from the published description alone.", "risk_confidence": "medium"}
    return {"risk_score": 25, "risk_level": "Limited detail", "risk_rationale": "The public record contains a violation code without enough descriptive text to estimate severity precisely.", "risk_confidence": "low"}


def assess_violation(raw: str | None, *, official_description: str | None = None, code: str | None = None) -> dict[str, Any]:
    parsed_code, parsed_desc = parse_violation(raw)
    desc = _text(official_description) or parsed_desc
    violation_code = _text(code) or parsed_code or (_text(raw) if re.fullmatch(r"\d{2,6}", _text(raw)) else "")
    category = categorize(desc)
    return {"code": violation_code, "official_description": desc or None, **category, **severity(desc)}


def risk_band(score: int) -> str:
    if score >= 90:
        return "Critical"
    if score >= 75:
        return "High"
    if score >= 50:
        return "Elevated"
    if score >= 25:
        return "Moderate"
    if score > 0:
        return "Low"
    return "No cited risk"


def assess_inspection(violations: list[dict[str, Any]], *, status: str = "", violation_count: int = 0) -> dict[str, Any]:
    scores = sorted([int(v.get("risk_score") or 0) for v in violations if v.get("risk_score") is not None], reverse=True)
    if scores:
        score = min(100, round(scores[0] + sum(scores[1:]) * 0.12))
        confidence = "high" if all(v.get("risk_confidence") == "high" for v in violations) else "medium"
    elif violation_count:
        score = min(60, 25 + max(0, violation_count - 1) * 7)
        confidence = "low"
    else:
        score = 0
        confidence = "high"

    status_norm = _text(status).lower()
    if "closure" in status_norm or "closed" in status_norm:
        score = max(score, 95)
    elif "conditional" in status_norm:
        score = max(score, 80)

    ranked = sorted(violations, key=lambda v: int(v.get("risk_score") or 0), reverse=True)
    if not ranked:
        summary = "No violations were cited in the published inspection record." if score == 0 else "Violations were cited, but the public record does not include enough descriptive detail for a precise risk summary."
    else:
        primary = ranked[0]
        summary = f"Primary concern: {primary.get('normalized_category', 'food-safety issue').lower()}."
        if len(ranked) > 1:
            summary += f" {len(ranked)-1} additional finding{'s' if len(ranked) != 2 else ''} also contributed to the inspection risk index."

    return {"risk_score": score, "risk_level": risk_band(score), "risk_confidence": confidence, "risk_summary": summary, "methodology": "Relative foodborne-illness risk index; not a probability and not an official SFDPH score."}
