from __future__ import annotations

import json
import re
from typing import Any

# Safe parser for grouped DataSF findings.
#
# Restaurant detail records can contain long violation strings. The legacy parser
# used a whole-string regex with nested repetition and look-ahead, which could spend
# many seconds backtracking on certain payloads. This implementation first finds the
# literal ` - ` separators, then applies a code-group regex only to a fixed-size
# window immediately before each separator. Runtime is therefore bounded by input
# length and a constant-size validation window.
_CODE_RE = r"[A-Za-z]?\d{2,}[\d.\-]*(?:\([^)]{0,80}\))?"
_CODE_GROUP_SUFFIX_RE = re.compile(
    rf"(?:^|,\s*)(?P<codes>{_CODE_RE}(?:,\s*{_CODE_RE}){{0,40}})\s*$"
)
_MAX_CODE_WINDOW = 1200


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


def _finding_starts(text: str) -> list[tuple[int, int, str]]:
    starts: list[tuple[int, int, str]] = []
    search_from = 0
    while True:
        separator = text.find(" - ", search_from)
        if separator < 0:
            break

        window_start = max(0, separator - _MAX_CODE_WINDOW)
        prefix = text[window_start:separator]
        match = _CODE_GROUP_SUFFIX_RE.search(prefix)
        if match:
            code_start = window_start + match.start("codes")
            description_start = separator + 3
            codes = re.sub(r"\s+", " ", match.group("codes").strip().strip(" ,"))
            starts.append((code_start, description_start, codes))

        search_from = separator + 3
    return starts


def parse_grouped_findings(value: Any) -> list[dict[str, str]]:
    """Parse grouped code-list + description findings without whole-string regex scans."""
    results: list[dict[str, str]] = []
    for raw in _flatten(value):
        # Pipe-separated values are uncommon but supported by the legacy parser.
        for segment in raw.split("|"):
            text = segment.strip()
            if not text:
                continue
            starts = _finding_starts(text)
            for index, (code_start, description_start, codes) in enumerate(starts):
                description_end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
                desc = re.sub(r"\s+", " ", text[description_start:description_end].strip().strip(" ,"))
                if codes and desc:
                    results.append({"code": codes, "official_description": desc})
    return results
