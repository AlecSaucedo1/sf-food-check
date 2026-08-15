from __future__ import annotations

RULES = [
    (["temperature", "cold hold", "hot hold", "refriger"], "Food temperature", "Food was not maintained within a required food-safety temperature range."),
    (["handwash", "hand wash", "hand washing"], "Hand washing", "A handwashing facility or required handwashing practice did not meet requirements."),
    (["vermin", "rodent", "cockroach", "pest", "insect"], "Pests", "Inspectors observed evidence of pests or a condition that could support pest activity."),
    (["cross contamination", "cross-contamination", "raw", "ready-to-eat"], "Cross-contamination", "Food handling created or could create a contamination risk between raw and ready-to-eat items."),
    (["sanitize", "sanitiz", "clean", "food-contact", "food contact"], "Cleaning & sanitation", "A cleaning or sanitizing requirement was not met."),
    (["water", "plumb", "sewage", "sink"], "Water & plumbing", "A water, sink, drainage, or plumbing requirement was not met."),
    (["storage", "stored", "covered", "container"], "Food storage", "Food storage did not fully meet requirements intended to protect it from contamination."),
    (["floor", "wall", "ceiling", "equipment", "repair"], "Facility condition", "A facility surface, fixture, or piece of equipment required cleaning, maintenance, or repair."),
    (["certificate", "manager", "procedure", "haccp", "plan"], "Food-safety procedures", "A required food-safety procedure, credential, or plan was missing or incomplete."),
    (["employee", "personal", "glove", "hair"], "Employee practices", "An employee food-safety practice did not meet requirements."),
]


def categorize(official_description: str | None) -> dict[str, str | None]:
    text = (official_description or "").lower()
    for words, category, consumer in RULES:
        if any(w in text for w in words):
            return {"normalized_category": category, "consumer_description": consumer}
    return {"normalized_category": "Other food-safety requirement", "consumer_description": None}
