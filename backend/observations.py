from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from typing import Any

from .taxonomy import risk_band

OBSERVATION_MODEL_VERSION = "2026.08.15.1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS violation_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id TEXT NOT NULL,
    permit_number TEXT NOT NULL,
    inspection_date TEXT NOT NULL,
    violation_code TEXT,
    observation_text TEXT NOT NULL,
    corrective_action TEXT,
    report_url TEXT NOT NULL,
    source_label TEXT NOT NULL DEFAULT 'Official SFDPH inspection report',
    source_type TEXT NOT NULL DEFAULT 'verified_official_report',
    sequence_number INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(inspection_id, violation_code, observation_text, report_url)
);
CREATE INDEX IF NOT EXISTS idx_observations_inspection ON violation_observations(inspection_id);
CREATE INDEX IF NOT EXISTS idx_observations_permit_date ON violation_observations(permit_number, inspection_date);
"""

_CODE_TOKEN_RE = re.compile(r"[A-Za-z]?\d{2,}[\d.\-]*(?:\([^)]*\))?")


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def ensure_observation_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _code_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    for raw in _CODE_TOKEN_RE.findall(_text(value)):
        token = re.sub(r"\s+", "", raw).upper()
        if not token:
            continue
        tokens.add(token)
        tokens.add(re.sub(r"\([^)]*\)", "", token))
    return {token for token in tokens if token}


def codes_match(left: Any, right: Any) -> bool:
    a, b = _code_tokens(left), _code_tokens(right)
    return bool(a and b and a.intersection(b))


def assess_observation(
    observation_text: str | None,
    *,
    parent_score: int | None = None,
    parent_category: str | None = None,
) -> dict[str, Any]:
    """Grade the specific condition described by an inspector observation.

    This is an independent consumer interpretation. It intentionally does not
    alter the official SFDPH finding or status and it is not a probability of illness.
    """
    text = _text(observation_text).lower()
    parent = int(parent_score or 0)

    def has(*phrases: str) -> bool:
        return any(phrase in text for phrase in phrases)

    if not text:
        score = parent or 25
        confidence = "low"
        rationale = "No observation narrative was available, so severity falls back to the cited violation context."
    elif has("sewage backup", "sewage overflow", "wastewater overflow", "sewage on", "sewage in"):
        score = 98
        confidence = "high"
        rationale = "Sewage or wastewater in a food facility can directly contaminate food, hands, equipment, and food-contact surfaces."
    elif has("vomiting", "vomit", "diarrhea") and has("employee", "food worker", "worker"):
        score = 96
        confidence = "high"
        rationale = "An ill food worker with vomiting or diarrhea symptoms creates a direct pathway for highly transmissible pathogens to reach food or surfaces."
    elif (has("rodent droppings", "mouse droppings", "rat droppings", "feces", "faeces") and has("food", "prep table", "food-contact", "food contact", "utensil", "equipment")) or has("food contaminated", "contaminated food"):
        score = 93
        confidence = "high"
        rationale = "The observation describes direct or near-direct contamination of food or food-contact areas."
    elif has("raw") and has("ready-to-eat", "ready to eat", "cooked food"):
        score = 90
        confidence = "high"
        rationale = "The observed storage or handling condition creates a direct cross-contamination pathway from raw food to ready-to-eat food."
    elif has("bare hand", "bare-hand") and has("ready-to-eat", "ready to eat", "food"):
        score = 88
        confidence = "high"
        rationale = "Bare-hand contact with ready-to-eat food can directly transfer pathogens to food that will not receive another kill step."
    elif has("live cockroach", "live roach", "rodent droppings", "mouse droppings", "rat droppings", "dead mouse", "dead rat", "rodent activity", "vermin activity"):
        score = 84
        confidence = "high"
        rationale = "Active vermin or fresh evidence of vermin creates a meaningful contamination risk even when direct food contamination is not described."
    elif has("cold holding", "cold hold", "hot holding", "hot hold", "cooling", "refrigerator", "refrigeration", "degrees f", "°f", "temperature"):
        score = 82
        confidence = "high"
        rationale = "The observation describes a time or temperature control failure that can allow pathogens to grow or survive."
    elif has("handwash", "hand wash", "handwashing") and has("blocked", "obstructed", "no soap", "without soap", "no paper towel", "not accessible", "inaccessible", "no hot water", "no warm water"):
        score = 78
        confidence = "high"
        rationale = "The observed handwashing deficiency can prevent effective hand hygiene during food preparation."
    elif has("sanitizer", "sanitizing", "sanitization", "food-contact surface", "food contact surface", "unclean utensil", "unclean equipment"):
        score = 70
        confidence = "high"
        rationale = "The observation describes a food-contact cleaning or sanitizing problem that can transfer contamination to food."
    elif has("flies", "fly activity", "cockroach", "roach", "rodent", "vermin", "pest"):
        score = 66
        confidence = "medium"
        rationale = "The observation indicates pest activity or pest-control failure with an indirect but meaningful contamination pathway."
    elif has("plumbing", "leak", "drain", "sink"):
        score = 52
        confidence = "medium"
        rationale = "The observed plumbing or sink condition can interfere with sanitation and safe food operations, depending on location and extent."
    elif has("floor", "wall", "ceiling", "coving", "door gap", "hole", "good repair", "damaged", "cracked", "peeling"):
        score = 40
        confidence = "medium"
        rationale = "The observation is primarily structural or maintenance-related, which can make cleaning or pest exclusion more difficult."
    elif has("certificate", "food safety manager", "permit", "documentation", "label", "signage", "record"):
        score = 20
        confidence = "medium"
        rationale = "The observation is primarily administrative or documentation-related rather than a direct contamination pathway."
    else:
        score = parent or 35
        confidence = "medium" if parent else "low"
        category = _text(parent_category).lower() or "the cited violation"
        rationale = f"The narrative does not contain a stronger condition-specific hazard marker, so severity follows the context of {category}."

    score = max(0, min(100, int(score)))
    return {
        "severity_score": score,
        "severity_level": risk_band(score),
        "severity_confidence": confidence,
        "severity_rationale": rationale,
        "severity_model_version": OBSERVATION_MODEL_VERSION,
        "methodology": "Independent severity interpretation of the inspector's specific observation; not an official SFDPH score and not a probability of illness.",
    }


def _resolve_inspection_id(con: sqlite3.Connection, item: dict[str, Any]) -> str:
    explicit = _text(item.get("inspection_id"))
    if explicit:
        row = con.execute("SELECT inspection_id FROM inspections WHERE inspection_id=?", (explicit,)).fetchone()
        if row:
            return str(row[0])
        raise ValueError(f"Unknown inspection_id: {explicit}")

    permit = _text(item.get("permit_number"))
    inspection_date = _text(item.get("inspection_date"))[:10]
    inspection_type = _text(item.get("inspection_type"))
    if not permit or not inspection_date:
        raise ValueError("permit_number and inspection_date are required when inspection_id is not provided")

    if inspection_type:
        rows = con.execute(
            "SELECT inspection_id FROM inspections WHERE permit_number=? AND inspection_date=? AND inspection_type=? ORDER BY inspection_id",
            (permit, inspection_date, inspection_type),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT inspection_id FROM inspections WHERE permit_number=? AND inspection_date=? ORDER BY inspection_id",
            (permit, inspection_date),
        ).fetchall()
    if len(rows) == 1:
        return str(rows[0][0])
    if not rows:
        raise ValueError(f"No inspection found for permit {permit} on {inspection_date}")
    raise ValueError(f"Multiple inspections found for permit {permit} on {inspection_date}; include inspection_type or inspection_id")


def import_observations(con: sqlite3.Connection, items: list[dict[str, Any]]) -> int:
    ensure_observation_schema(con)
    imported = 0
    for item in items:
        observation = _text(item.get("observation_text") or item.get("observation") or item.get("inspector_observation"))
        report_url = _text(item.get("report_url"))
        if not observation:
            raise ValueError("observation_text is required")
        if not report_url:
            raise ValueError("report_url is required so every observation retains official-report provenance")

        inspection_id = _resolve_inspection_id(con, item)
        source = con.execute(
            "SELECT permit_number, inspection_date FROM inspections WHERE inspection_id=?",
            (inspection_id,),
        ).fetchone()
        permit, inspection_date = str(source[0]), str(source[1])
        code = _text(item.get("violation_code") or item.get("code"))
        corrective_action = _text(item.get("corrective_action")) or None
        source_label = _text(item.get("source_label")) or "Official SFDPH inspection report"
        sequence_number = int(item.get("sequence_number") or 0)

        before = con.total_changes
        con.execute(
            """
            INSERT OR IGNORE INTO violation_observations
              (inspection_id, permit_number, inspection_date, violation_code, observation_text,
               corrective_action, report_url, source_label, source_type, sequence_number)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                inspection_id, permit, inspection_date, code or None, observation,
                corrective_action, report_url, source_label, "verified_official_report", sequence_number,
            ),
        )
        if con.total_changes > before:
            imported += 1

        # Preserve the report link in the existing inspection-level provenance layer.
        con.execute(
            """
            INSERT INTO report_enrichment
              (permit_number, inspection_date, report_url, inspector_comments, corrective_action, comment_source, source_label)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(permit_number, inspection_date) DO UPDATE SET
              report_url=CASE WHEN excluded.report_url<>'' THEN excluded.report_url ELSE report_enrichment.report_url END,
              source_label=CASE WHEN excluded.source_label<>'' THEN excluded.source_label ELSE report_enrichment.source_label END,
              imported_at=CURRENT_TIMESTAMP
            """,
            (permit, inspection_date, report_url, None, None, "verified_observation_import", source_label),
        )
    con.commit()
    return imported


def attach_observations(con: sqlite3.Connection, result: dict[str, Any]) -> dict[str, Any]:
    ensure_observation_schema(con)
    inspections = result.get("inspections") or []
    ids = [str(item.get("inspection_id") or "") for item in inspections if item.get("inspection_id")]
    if not ids:
        return result

    placeholders = ",".join("?" for _ in ids)
    rows = con.execute(
        f"""
        SELECT inspection_id, violation_code, observation_text, corrective_action,
               report_url, source_label, source_type, sequence_number
        FROM violation_observations
        WHERE inspection_id IN ({placeholders})
        ORDER BY inspection_id, sequence_number, id
        """,
        ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["inspection_id"])].append(dict(row))

    for inspection in inspections:
        inspection["report_observations"] = grouped.get(str(inspection.get("inspection_id") or ""), [])
    return result


def observation_metrics(con: sqlite3.Connection) -> dict[str, Any]:
    ensure_observation_schema(con)
    records = con.execute("SELECT COUNT(*) FROM violation_observations").fetchone()[0]
    inspections = con.execute("SELECT COUNT(DISTINCT inspection_id) FROM violation_observations").fetchone()[0]
    return {"observation_records": int(records), "inspections_with_observations": int(inspections)}
