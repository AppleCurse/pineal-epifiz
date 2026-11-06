"""Shared validation for confidence-shaped values and epistemic evidence status.

A confidence field is a finite score in [0, 1], not proof that an output is
correct or calibrated. Invalid values fail closed rather than being clamped to
an apparently meaningful probability.

Input presence (``input_data_present``) is distinct from corroborated evidence
verification (``evidence_verification_status``). Legacy ``data_confidence=True``
must not be promoted to ``evidence_verification_status="verified"`` without
explicit verification proof.
"""

from __future__ import annotations

import math
from typing import Any, Literal

EvidenceVerificationStatus = Literal["verified", "unverified", "not_applicable", "unknown"]
VALID_EVIDENCE_VERIFICATION_STATUSES: frozenset[str] = frozenset(
    {"verified", "unverified", "not_applicable", "unknown"}
)


def normalize_confidence(value: Any) -> tuple[float, bool]:
    """Return ``(score, valid)``; invalid/non-finite/out-of-range input is 0.0."""
    if isinstance(value, bool):
        return 0.0, False
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0, False
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        return 0.0, False
    return score, True


def normalize_evidence_verification_status(
    value: Any,
    *,
    has_verified_proof: bool = False,
) -> EvidenceVerificationStatus:
    """Normalize ``evidence_verification_status`` with fail-closed proof check."""
    if not isinstance(value, str):
        return "unknown"
    cleaned = value.strip().lower()
    if cleaned == "verified":
        return "verified" if has_verified_proof else "unverified"
    if cleaned == "unverified":
        return "unverified"
    if cleaned == "not_applicable":
        return "not_applicable"
    if cleaned == "unknown":
        return "unknown"
    return "unknown"
