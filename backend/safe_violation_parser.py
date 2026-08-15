from __future__ import annotations

import json
import re
from typing import Any

# Safe parser for grouped DataSF findings.
#
# Restaurant detail records can contain long violation strings. The legacy parser
# used a whole-string regex with nested repetition and look-ahead, which could spend
# many seconds backtracking on certain payloads. This implementation finds literal
# ` - ` separators, then walks backward through top-level comma-separated code tokens.
# It never regex-searches narrative text.
_CODE_TOKEN_RE = re.compile(r"[A-Za-z]?\d{2,}[\d.\-]*(?:\([^)]{0,80}\))?")
_MAX_CODE_WINDOW = 1200
_MAX_CODES_PER_FINDING = 40


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


def _top_level_parts(text: str) -> list[tuple[int, int, str]]:
    """Split on commas outside parentheses while retaining source offsets."""
    parts: list[tuple[int, int, str]] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append((start, index, text[start:index]))
            start = index + 1
    parts.append((start, len(text), text[start:]))
    return parts


def _code_group_suffix(prefix: str) -> tuple[int, str] | None:
    """Return the trailing code-group start and normalized text, if present."""
    parts = _top_level_parts(prefix)
    codes: list[str] = []
    code_start: int | None = None

    for start, _end, raw_part in reversed(parts):
        token = raw_part.strip()
        if not token or not _CODE_TOKEN_RE.fullmatch(token):
            break
        leading = len(raw_part) - len(raw_part.lstrip())
        code_start = start + leading
        codes.append(token)
        if len(codes) >= _MAX_CODES_PER_FINDING:
            break

    if code_start is None:
        return None
    codes.reverse()
    return code_start, ", ".join(codes)


def _finding_starts(text: str) -> list[tuple[int, int, str]]:
    starts: list[tuple[int, int, str]] = []
    search_from = 0
    while True:
        separator = text.find(" - ", search_from)
        if separator < 0:
            break

        window_start = max(0, separator - _MAX_CODE_WINDOW)
        prefix = text[window_start:separator]
        suffix = _code_group_suffix(prefix)
        if suffix:
            local_code_start, codes = suffix
            starts.append((window_start + local_code_start, separator + 3, codes))

        search_from = separator + 3
    return starts


def parse_grouped_findings(value: Any) -> list[dict[str, str]]:
    """Parse grouped code-list + description findings in linear time."""
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
