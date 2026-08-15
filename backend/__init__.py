"""Backend package initialization.

Install the bounded grouped-violation parser before other backend modules import the
public taxonomy helpers. This keeps restaurant detail rendering safe for unusually
large or malformed DataSF violation strings while preserving the existing risk model.
"""

from . import taxonomy as _taxonomy
from .safe_violation_parser import parse_grouped_findings as _safe_parse_grouped_findings

_taxonomy.parse_grouped_findings = _safe_parse_grouped_findings
