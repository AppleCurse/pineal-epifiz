"""Shared validation for confidence-shaped values.

A confidence field is a finite score in [0, 1], not proof that an output is
correct or calibrated. Invalid values fail closed rather than being clamped to
an apparently meaningful probability.
"""

from __future__ import annotations

import math
from typing import Any


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
