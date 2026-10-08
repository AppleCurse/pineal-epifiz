"""Canonical, epistemically typed evidence contract.

The contract preserves what a source actually emitted. It deliberately keeps
engine scores separate from calibrated confidence; consumers must not infer a
probability from a numeric source metric.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field

from agent_core.domain.pillar_models import EvidenceStatus, StrictModel


EpistemicType = Literal["observation", "absence", "inference", "strategy"]
TimelineEpistemicType = Literal["observation", "absence", "inference"]
TemporalBasis = Literal["observed_at", "window_start", "window_end", "undated"]


class EvidenceItem(StrictModel):
    """One source-scoped statement with an explicit epistemic classification."""

    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{20}$")
    epistemic_type: EpistemicType
    source_engine: str = Field(min_length=1)
    source_status: EvidenceStatus | None = Field(
        default=None,
        description=(
            "Source-native status when the source provides one; None means unavailable, "
            "not an independent confidence or truth verdict."
        ),
    )
    content: str = Field(min_length=1)
    provenance_refs: list[str] = Field(default_factory=list)
    scope: dict[str, Any] | None = None
    observed_at: datetime | None = Field(
        default=None,
        description=(
            "Source-reported timestamp with the source engine's semantics preserved; "
            "it may be representative rather than an exact event onset."
        ),
    )
    window_start: datetime | None = None
    window_end: datetime | None = None
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Calibrated confidence only; source scores must remain in source_metrics.",
    )
    source_metrics: dict[str, Any] | None = None


class EvidenceTimelineEntry(StrictModel):
    """A type-gated, neutral view of one canonical item in temporal order."""

    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{20}$")
    timeline_at: datetime | None = None
    temporal_basis: TemporalBasis
    epistemic_type: TimelineEpistemicType
    epistemic_note: str
    source_engine: str = Field(min_length=1)
    source_status: EvidenceStatus | None = Field(
        default=None,
        description="Source-native status when available; not an independent truth verdict.",
    )
    content: str = Field(min_length=1)
    provenance_refs: list[str] = Field(default_factory=list)
    scope: dict[str, Any] | None = None
    observed_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    source_metrics: dict[str, Any] | None = None


class EvidenceTimeline(StrictModel):
    """Validated timeline envelope; strategies and malformed items are omitted."""

    schema_version: Literal["evidence-timeline-v1"] = "evidence-timeline-v1"
    entries: list[EvidenceTimelineEntry] = Field(default_factory=list)
    excluded_strategy_count: int = Field(default=0, ge=0)
    rejected_item_count: int = Field(default=0, ge=0)
    source_status_note: Literal[
        "Copied when source-reported; missing status is not synthesized and is not an independent truth/verification verdict."
    ] = "Copied when source-reported; missing status is not synthesized and is not an independent truth/verification verdict."

    model_config = ConfigDict(extra="forbid", frozen=True)
