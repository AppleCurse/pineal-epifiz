"""Type-gated, neutral ordering for canonical pillar evidence.

This service does not interpret evidence or write a narrative. It excludes
strategy items, preserves source labels/provenance, and keeps absences and
hypotheses explicitly scoped and labeled.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import ValidationError

from agent_core.domain.evidence_models import (
    EvidenceItem,
    EvidenceTimeline,
    EvidenceTimelineEntry,
)

_EPISTEMIC_NOTES = {
    "observation": "Source-emitted observation/measurement; not independently verified.",
    "absence": (
        "Absence signal scoped to its stated corpus; not a life-event or psychological conclusion."
    ),
    "inference": "Unverified inference; not an observed event or established cause.",
}


def _sort_key(entry: EvidenceTimelineEntry) -> tuple[int, datetime, str]:
    at = entry.timeline_at
    if at is None:
        return (1, datetime.max.replace(tzinfo=timezone.utc), entry.evidence_id)
    normalized = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)
    return (0, normalized, entry.evidence_id)


def _entry(item: EvidenceItem) -> EvidenceTimelineEntry:
    if item.observed_at is not None:
        timeline_at = item.observed_at
        temporal_basis = "observed_at"
    elif item.window_start is not None:
        timeline_at = item.window_start
        temporal_basis = "window_start"
    elif item.window_end is not None:
        timeline_at = item.window_end
        temporal_basis = "window_end"
    else:
        timeline_at = None
        temporal_basis = "undated"

    scope = item.scope or {}
    tier2_note = None
    if scope.get("canonicalization") == "tier2-evidence-adapter-v1":
        if item.source_engine == "human_behavior" and item.epistemic_type == "observation":
            tier2_note = (
                "Agent-labeled observation; not independently verified or source-linked."
            )
        elif item.source_engine == "human_behavior" and item.epistemic_type == "inference":
            tier2_note = (
                "Agent interpretation; unverified and not an observed event or established cause."
            )
    epistemic_note = tier2_note or _EPISTEMIC_NOTES[item.epistemic_type]
    return EvidenceTimelineEntry(
        evidence_id=item.evidence_id,
        timeline_at=timeline_at,
        temporal_basis=temporal_basis,
        epistemic_type=item.epistemic_type,
        epistemic_note=epistemic_note,
        source_engine=item.source_engine,
        source_status=item.source_status,
        content=item.content,
        provenance_refs=list(item.provenance_refs),
        scope=item.scope,
        observed_at=item.observed_at,
        window_start=item.window_start,
        window_end=item.window_end,
        source_metrics=item.source_metrics,
    )


def build_evidence_timeline(items: Iterable[EvidenceItem | dict[str, Any]] | None) -> EvidenceTimeline:
    """Build a chronological view from valid canonical evidence only.

    ``strategy`` is deliberately not a timeline type. Missing, malformed, or
    untyped raw findings are rejected rather than promoted to evidence.
    """
    if items is None:
        return EvidenceTimeline()

    entries: list[EvidenceTimelineEntry] = []
    excluded_strategy_count = 0
    rejected_item_count = 0

    for raw in items:
        if isinstance(raw, EvidenceItem):
            item = raw
        elif isinstance(raw, dict):
            try:
                item = EvidenceItem.model_validate(raw)
            except ValidationError:
                rejected_item_count += 1
                continue
        else:
            rejected_item_count += 1
            continue

        if item.epistemic_type == "strategy":
            excluded_strategy_count += 1
            continue
        entries.append(_entry(item))

    entries.sort(key=_sort_key)
    return EvidenceTimeline(
        entries=entries,
        excluded_strategy_count=excluded_strategy_count,
        rejected_item_count=rejected_item_count,
    )
