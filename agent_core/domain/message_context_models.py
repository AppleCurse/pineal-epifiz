"""Prompt-neutral decision context for controlled evidence handoff.

This contract is intentionally smaller than EvidenceItem: message generation
receives only provenance-bearing observations, never absences, inferences, or
strategy. It keeps the evidence schema decoupled from prompt wording.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field

from agent_core.domain.pillar_models import EvidenceStatus, StrictModel
from agent_core.domain.evidence_models import TemporalBasis


class MessageEvidenceContextItem(StrictModel):
    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{20}$")
    epistemic_type: Literal["observation"] = "observation"
    epistemic_note: Literal[
        "Source-emitted observation/measurement; not independently verified."
    ] = "Source-emitted observation/measurement; not independently verified."
    content: str = Field(min_length=1)
    source_engine: str = Field(min_length=1)
    source_status: EvidenceStatus | None = None
    timeline_at: datetime | None = None
    temporal_basis: TemporalBasis
    observed_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    provenance_refs: list[str] = Field(min_length=1)
    scope: dict[str, Any] | None = None


class MessageEvidenceContext(StrictModel):
    schema_version: Literal["message-evidence-context-v1"] = "message-evidence-context-v1"
    context_id: str = Field(pattern=r"^ctx_[0-9a-f]{20}$")
    build_status: Literal["ready", "empty", "failed"]
    policy: Literal["provenance-bearing-observations-only"] = "provenance-bearing-observations-only"
    items: list[MessageEvidenceContextItem] = Field(default_factory=list)
    excluded_counts: dict[str, int] = Field(default_factory=dict)
    source_status_note: Literal[
        "Copied when source-reported; missing status is not synthesized and is not an independent truth/verification verdict."
    ] = "Copied when source-reported; missing status is not synthesized and is not an independent truth/verification verdict."

    model_config = ConfigDict(extra="forbid", frozen=True)
