"""Güvenlik kilitleri.

Buradaki tek kilit: **ÇOCUK KIRMIZI ÇİZGİSİ** (`minor_gate.py`).
18 yaş altı — kayıp/yaralanma istisnası dışında — hiçbir koşulda araştırılamaz.
Yetişkinler için sistem hiçbir engel koymaz; karar mercii operatördür.
"""

from __future__ import annotations

from agent_core.safety.minor_gate import (  # noqa: F401
    ALLOWED_MINOR_CASE_TYPES,
    MIN_COUNCIL_APPROVALS,
    MIN_REASON_CHARS,
    MINOR_AGE_LIMIT,
    MinorCaseContext,
    MinorCaseLedger,
    MinorDecision,
    MinorGate,
    coerce_minor_case,
)

__all__ = [
    "MINOR_AGE_LIMIT",
    "MIN_COUNCIL_APPROVALS",
    "MIN_REASON_CHARS",
    "ALLOWED_MINOR_CASE_TYPES",
    "MinorCaseContext",
    "MinorDecision",
    "MinorGate",
    "MinorCaseLedger",
    "coerce_minor_case",
]
