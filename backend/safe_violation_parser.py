from __future__ import annotations

import json
import re
from typing import Any

# Bounded parser for grouped DataSF findings.
#
# The previous parser used nested repetition plus a variable-length look-ahead over
# the entire description. Certain long violation strings could therefore consume a
# web worker for many seconds and cause Render's proxy to return 502/504 errors.
# This expression only locates the beginning of each finding. Descriptions are then
# sliced between starts, keeping runtime effectively linear in the input length.
_CODE_RE = r"[A-Za-z]?\d{2,}[\d.\-]*(?:\([^)]{0,80}\))?"
_FINDING_START_RE = re.compile(
    rf"(?:^|,\s*)(?P<codes>{_CODE_RE}(?:,\s*{_CODE_RE}){{0,40}})\s+-\s+"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


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
        for key in (
            "code",
            "violation_code",
            "id",
            "description",
            "violation_description",
            "name",
            "text",
            "value",
        ):
            if key in value and value[key] not in (None, ""):
                ordered.extend(_flatten(value[key]))
        if ordered:
            return ordered
        return [_text(item) for item in value.values() if _text(item)]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [_text(value)] if _text(value) else []


def parse_grouped_findings(value: Any) -> list[dict[str, str]]:
    """Parse grouped code-list + description findings in bounded linear time."""
    results: list[dict[str, str]] = []
    for raw in _flatten(value):
        for segment in re.split(r"\s*\|\s*", raw):
            text = segment.strip()
            if not text:
                continue
            matches = list(_FINDING_START_RE.finditer(text))
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                codes = re.sub(r"\s+", " ", match.group("codes").strip().strip(" ,"))
                desc = re.sub(r"\s+", " ", text[match.end():end].strip().strip(" ,"))
                if codes and desc:
                    results.append({"code": codes, "official_description": desc})
    return results
