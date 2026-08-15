from __future__ import annotations

import json
import re
from typing import Any

CATEGORY_RULES = [
    (["ill employee", "sick employee", "employee illness", "vomit", "diarrhea"], "Employee illness", "A sick-food-worker control was not met, creating a direct contamination risk."),
    (["bare hand", "bare-hand", "cross contamination", "cross-contamination"], "Cross-contamination", "Food handling could transfer pathogens to ready-to-eat food."),
    (["undercook", "inadequate cooking", "improper cooking", "reheat", "pasteur", "parasite destruction"], "Cooking & reheating", "Food did not fully meet a required pathogen-kill step such as cooking, reheating, or parasite destruction."),
    (["cold hold", "hot hold", "temperature", "cooling", "refriger", "time as a public health control"], "Temperature control", "Food was not kept within time or temperature controls intended to prevent pathogen growth."),
    (["unsafe source", "unapproved source", "approved source", "shellstock", "shellfish tag", "adulterat"], "Food source & contamination", "Food source, traceability, or contamination controls did not meet safety requirements."),
    (["handwash", "hand wash", "hand washing", "soap", "paper towel"], "Hand washing", "A handwashing facility or required handwashing practice did not meet requirements."),
    (["sewage", "wastewater", "potable water", "water supply"], "Water & sewage", "A water or sewage condition could directly affect food safety."),
    (["rodent", "cockroach", "evidence of vermin", "vermin infestation", "pest activity", "insect infestation", "flies", "fly infestation"], "Pests", "Inspectors observed pests or evidence of pest activity that could contaminate food or food-contact areas."),
    (["vermin proof", "litter or rubbish", "open-air barbecue", "open-air barbecues", "premises of each food facility"], "Facility sanitation & pest prevention", "The facility did not fully meet housekeeping, separation, enclosure, or pest-prevention requirements."),
    (["walls / ceilings", "wall surfaces", "floor surfaces", "base coving", "fully enclosed", "good repair"], "Facility condition & repair", "Floors, walls, ceilings, enclosure, or other facility surfaces did not fully meet cleanability or repair requirements."),
    (["sanitize", "sanitiz", "unclean food-contact", "food-contact surface", "food contact surface", "utensil"], "Food-contact sanitation", "A food-contact surface, utensil, or sanitizing process did not meet requirements."),
    (["thaw", "food storage", "protected from contamination", "covered food", "food container"], "Food storage & protection", "Food storage or protection practices did not fully prevent contamination or unsafe handling."),
    (["plumb", "sink", "drain"], "Plumbing & sinks", "A sink, drain, or plumbing requirement was not met."),
    (["clean", "equipment", "garbage", "refuse", "repair", "maintain", "floor", "wall", "ceiling", "ventilation", "litter", "rubbish"], "Facility cleanliness & maintenance", "A cleaning, maintenance, refuse, ventilation, or facility-condition requirement was not met."),
    (["certificate", "manager", "procedure", "haccp", "plan", "permit", "documentation", "label", "signage"], "Food-safety procedures", "A required food-safety procedure, credential, label, permit, or record was missing or incomplete."),
    (["employee", "personal", "glove", "hair"], "Employee practices", "An employee food-safety practice did not meet requirements."),
]

SEVERITY_RULES = [
    (95, "Critical", ["ill employee", "sick employee", "employee illness", "vomit", "diarrhea", "sewage", "wastewater overflow", "unsafe source", "unapproved source", "adulterat", "cross contamination", "cross-contamination", "bare hand", "undercook", "inadequate cooking", "improper cooking", "inadequate reheating", "parasite destruction"], "Direct pathway for pathogens to contaminate food or survive a required kill step."),
    (80, "High", ["cold hold", "hot hold", "temperature", "cooling", "refriger", "handwash", "hand wash", "hand washing", "sanitize", "sanitiz", "rodent", "cockroach", "evidence of vermin", "vermin infestation", "pest activity", "insect infestation", "flies", "shellstock", "shellfish tag", "potable water", "water supply"], "Strongly associated with contamination or pathogen growth when uncontrolled."),
    (55, "Elevated", ["vermin proof", "litter or rubbish", "open-air barbecue", "open-air barbecues", "premises of each food facility", "non-food items shall be stored and displayed separate"], "A sanitation or pest-prevention control was deficient, creating an indirect but meaningful contamination pathway."),
    (35, "Moderate", ["walls / ceilings", "wall surfaces", "floor surfaces", "base coving", "fully enclosed", "good repair"], "A structural or repair issue can make effective cleaning and pest exclusion more difficult, but is not itself evidence of food contamination."),
    (60, "Elevated", ["thaw", "protected from contamination", "food storage", "covered food", "food container", "wiping cloth", "utensil", "glove", "plumb", "sink", "drain"], "Can meaningfully increase foodborne-illness risk, depending on the specific condition."),
    (35, "Moderate", ["clean", "equipment", "garbage", "refuse", "repair", "maintain", "floor", "wall", "ceiling", "ventilation", "employee practice", "litter", "rubbish"], "Primarily a sanitation or operational control issue with a less direct illness pathway."),
    (15, "Low", ["certificate", "manager", "permit", "documentation", "label", "signage", "hair", "lighting", "procedure", "plan"], "Mostly administrative, documentation, or lower-immediacy food-safety concern."),
]

SINGLE_CODE_RE = r"[A-Za-z]?\d{2,}[\d.\-]*(?:\([^)]*\))?"
CODE_GROUP_RE = rf"{SINGLE_CODE_RE}(?:,\s*{SINGLE_CODE_RE})*"
GROUPED_FINDING_RE = re.compile(
    rf"(?P<codes>{CODE_GROUP_RE})\s+-\s+(?P<desc>.*?)(?=(?:[,|]\s*)?{CODE_GROUP_RE}\s+-\s+|\Z)",
    re.S,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _text(value).lower())


def _decode_collection(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return value


def _flatten(value: Any) -> list[str]:
    value = _decode_collection(value)
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        ordered: list[str] = []
        for k in ("code", "violation_code", "id", "description", "violation_description", "name", "text", "value"):
            if k in value and value[k] not in (None, ""):
                ordered.extend(_flatten(value[k]))
        if ordered:
            return ordered
        return [_text(v) for v in value.values() if _text(v)]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [_text(value)] if _text(value) else []


def _split_field(value: Any, *, comma: bool = False) -> list[str]:
    values = _flatten(value)
    out: list[str] = []
    pattern = r"\s*(?:\r?\n|;|\|)\s*"
    if comma:
        pattern = r"\s*(?:\r?\n|;|\||,)\s*"
    for value_text in values:
        pieces = re.split(pattern, value_text)
        out.extend(p.strip().strip("[]\"'") for p in pieces if p.strip().strip("[]\"'"))
    return out


def parse_grouped_findings(value: Any) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for raw in _flatten(value):
        for segment in re.split(r"\s*\|\s*", raw):
            matches = list(GROUPED_FINDING_RE.finditer(segment.strip()))
            for match in matches:
                codes = re.sub(r"\s+", " ", match.group("codes").strip())
                desc = re.sub(r"\s+", " ", match.group("desc").strip().strip(" ,"))
                if codes and desc:
                    results.append({"code": codes, "official_description": desc})
    return results


def parse_violation(raw: str | None) -> tuple[str, str]:
    value = _text(raw).strip("[]\"'")
    if not value:
        return "", ""
    grouped = parse_grouped_findings(value)
    if len(grouped) == 1:
        return grouped[0]["code"], grouped[0]["official_description"]
    m = re.match(rf"^\s*({SINGLE_CODE_RE})\s*[:\-–—|]\s*(.+)$", value)
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(rf"^\s*({SINGLE_CODE_RE})\s+(.+)$", value)
    if m:
        return m.group(1), m.group(2).strip()
    if re.fullmatch(SINGLE_CODE_RE, value):
        return value, ""
    return "", value


def extract_source_violations(raw_row: dict[str, Any] | None, fallback_codes: list[str] | None = None) -> list[dict[str, Any]]:
    """Recover violation code/description pairs from a raw DataSF inspection row."""
    raw_row = raw_row if isinstance(raw_row, dict) else {}
    code_values: list[tuple[str, str]] = []
    desc_values: list[tuple[str, str]] = []
    generic_values: list[tuple[str, str, str | None]] = []
    risk_values: list[str] = []
    results: list[dict[str, Any]] = []

    for field, value in raw_row.items():
        nk = _key(field)
        if "violation" not in nk:
            continue
        if "count" in nk or "numberof" in nk or nk.endswith("total"):
            continue

        risk_hint = None
        if "highrisk" in nk:
            risk_hint = "High Risk"
        elif "moderaterisk" in nk:
            risk_hint = "Moderate Risk"
        elif "lowrisk" in nk:
            risk_hint = "Low Risk"

        if "violationcodes" in nk or nk in {"violations", "violation"}:
            grouped = parse_grouped_findings(value)
            if grouped:
                for item in grouped:
                    results.append({**item, "official_risk_category": risk_hint, "source_field": field})
                continue

        if ("riskcategory" in nk or "risklevel" in nk or "severity" in nk) and not risk_hint:
            risk_values.extend(_split_field(value, comma=True))
            continue

        is_code = "code" in nk or nk.endswith("violationid") or nk.endswith("violationids")
        is_desc = any(token in nk for token in ("description", "desc", "detail", "finding", "text", "name"))
        if is_code and not is_desc:
            code_values.extend((v, field) for v in _split_field(value, comma=True))
        elif is_desc:
            desc_values.extend((v, field) for v in _split_field(value, comma=False))
        else:
            for v in _split_field(value, comma=False):
                code, desc = parse_violation(v)
                if code or desc:
                    generic_values.append((v, field, risk_hint))

    max_pairs = max(len(code_values), len(desc_values))
    for idx in range(max_pairs):
        raw_code = code_values[idx][0] if idx < len(code_values) else ""
        source_field = code_values[idx][1] if idx < len(code_values) else (desc_values[idx][1] if idx < len(desc_values) else "")
        parsed_code, code_desc = parse_violation(raw_code)
        desc = desc_values[idx][0] if idx < len(desc_values) else code_desc
        if desc:
            d_code, d_desc = parse_violation(desc)
            if not parsed_code and d_code:
                parsed_code = d_code
            desc = d_desc or desc
        risk = risk_values[idx] if idx < len(risk_values) else (risk_values[0] if len(risk_values) == 1 else None)
        if parsed_code or desc:
            results.append({
                "code": parsed_code or (raw_code if re.fullmatch(SINGLE_CODE_RE, raw_code) else ""),
                "official_description": desc or None,
                "official_risk_category": risk,
                "source_field": source_field,
            })

    for raw_value, source_field, risk in generic_values:
        grouped = parse_grouped_findings(raw_value)
        if grouped:
            for item in grouped:
                results.append({**item, "official_risk_category": risk, "source_field": source_field})
            continue
        code, desc = parse_violation(raw_value)
        if code or desc:
            results.append({
                "code": code,
                "official_description": desc or None,
                "official_risk_category": risk,
                "source_field": source_field,
            })

    if not results:
        for raw_value in fallback_codes or []:
            grouped = parse_grouped_findings(raw_value)
            if grouped:
                for item in grouped:
                    results.append({**item, "official_risk_category": None, "source_field": "normalized_violation_codes"})
                continue
            code, desc = parse_violation(raw_value)
            if code or desc:
                results.append({
                    "code": code or (raw_value if re.fullmatch(SINGLE_CODE_RE, _text(raw_value)) else ""),
                    "official_description": desc or None,
                    "official_risk_category": None,
                    "source_field": "normalized_violation_codes",
                })

    deduped: list[dict[str, Any]] = []
    by_code: dict[str, int] = {}
    seen_desc: set[str] = set()
    for item in results:
        code = _text(item.get("code"))
        desc = _text(item.get("official_description"))
        desc_key = re.sub(r"\s+", " ", desc.lower())
        if code and code in by_code:
            existing = deduped[by_code[code]]
            if not existing.get("official_description") and desc:
                existing["official_description"] = desc
                existing["source_field"] = item.get("source_field")
            if not existing.get("official_risk_category") and item.get("official_risk_category"):
                existing["official_risk_category"] = item.get("official_risk_category")
            continue
        if not code and desc_key and desc_key in seen_desc:
            continue
        if code:
            by_code[code] = len(deduped)
        if desc_key:
            seen_desc.add(desc_key)
        deduped.append(item)
    return deduped


def categorize(official_description: str | None) -> dict[str, str | None]:
    text = _text(official_description).lower()
    if not text:
        return {
            "normalized_category": "Official violation code",
            "consumer_description": "The public inspection row identifies a violation code but does not provide enough descriptive text to translate it reliably.",
        }
    for words, category, consumer in CATEGORY_RULES:
        if any(w in text for w in words):
            return {"normalized_category": category, "consumer_description": consumer}
    return {
        "normalized_category": "Other food-safety requirement",
        "consumer_description": "The inspection cited a food-safety requirement that does not map cleanly to one of the main foodborne-illness categories.",
    }


def severity(official_description: str | None, official_risk_category: str | None = None) -> dict[str, Any]:
    text = _text(official_description).lower()
    for score, level, words, rationale in SEVERITY_RULES:
        if any(w in text for w in words):
            base = {"risk_score": score, "risk_level": level, "risk_rationale": rationale, "risk_confidence": "high"}
            break
    else:
        if text:
            base = {
                "risk_score": 30,
                "risk_level": "Moderate",
                "risk_rationale": "The finding is relevant to food safety, but its direct connection to foodborne illness is not clear from the published description alone.",
                "risk_confidence": "medium",
            }
        else:
            base = {
                "risk_score": 25,
                "risk_level": "Limited detail",
                "risk_rationale": "The public inspection row contains a violation code without enough descriptive text to estimate severity precisely.",
                "risk_confidence": "low",
            }

    official = _text(official_risk_category).lower()
    if "high" in official and base["risk_score"] < 80:
        base.update(risk_score=80, risk_level="High", risk_confidence="high", risk_rationale="The official source identifies this as a high-risk violation directly relevant to public health.")
    elif "moderate" in official and base["risk_score"] < 50:
        base.update(risk_score=50, risk_level="Elevated", risk_confidence="high", risk_rationale="The official source identifies this as a moderate-risk public-health violation.")
    elif "low" in official and not text and base["risk_score"] > 20:
        base.update(risk_score=15, risk_level="Low", risk_confidence="high", risk_rationale="The official source identifies this as a low-risk violation with limited immediate public-health risk.")
    return base


def assess_violation(
    raw: str | None,
    *,
    official_description: str | None = None,
    code: str | None = None,
    official_risk_category: str | None = None,
    source_field: str | None = None,
) -> dict[str, Any]:
    parsed_code, parsed_desc = parse_violation(raw)
    desc = _text(official_description) or parsed_desc
    violation_code = _text(code) or parsed_code or (_text(raw) if re.fullmatch(SINGLE_CODE_RE, _text(raw)) else "")
    category = categorize(desc)
    return {
        "code": violation_code,
        "official_description": desc or None,
        "official_risk_category": _text(official_risk_category) or None,
        "source_field": source_field,
        **category,
        **severity(desc, official_risk_category),
    }


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
        confidences = {v.get("risk_confidence") for v in violations}
        confidence = "high" if confidences == {"high"} else ("low" if confidences == {"low"} else "medium")
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
    descriptive = [v for v in ranked if v.get("official_description")]
    if not ranked:
        summary = "No violations were cited in the published inspection record." if score == 0 else "Violations were cited, but the public record does not include enough descriptive detail for a precise risk summary."
    elif not descriptive:
        summary = f"{len(ranked)} violation code{'s were' if len(ranked) != 1 else ' was'} published, but descriptive findings were not available in the inspection row."
    else:
        primary = descriptive[0]
        summary = f"Primary concern: {primary.get('normalized_category', 'food-safety issue').lower()}."
        if len(ranked) > 1:
            summary += f" {len(ranked)-1} additional finding{'s' if len(ranked) != 2 else ''} also contributed to the inspection risk index."

    return {
        "risk_score": score,
        "risk_level": risk_band(score),
        "risk_confidence": confidence,
        "risk_summary": summary,
        "methodology": "Relative foodborne-illness risk index; not a probability and not an official SFDPH score.",
    }
