"""Deterministic, type-gated handoff from the neutral timeline to messaging."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from agent_core.domain.evidence_models import EvidenceTimeline, EvidenceTimelineEntry
from agent_core.domain.message_context_models import (
    MessageEvidenceContext,
    MessageEvidenceContextItem,
)

MAX_MESSAGE_CONTEXT_ITEMS = 3
MAX_MESSAGE_CONTEXT_CHARS = 3_000
_POLICY = "provenance-bearing-observations-only"


def _normalized_time(entry: EvidenceTimelineEntry) -> datetime:
    at = entry.timeline_at
    if at is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)


def _context_id(items: list[MessageEvidenceContextItem]) -> str:
    payload = {
        "policy": _POLICY,
        "items": [item.model_dump(mode="json") for item in items],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"ctx_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20]}"


def _empty_context(
    *, status: str = "empty", excluded_counts: dict[str, int] | None = None
) -> MessageEvidenceContext:
    return MessageEvidenceContext(
        context_id=_context_id([]),
        build_status=status,  # type: ignore[arg-type]
        items=[],
        excluded_counts=excluded_counts or {},
    )


def build_message_evidence_context(
    timeline: EvidenceTimeline | dict[str, Any] | None,
    *,
    max_items: int = MAX_MESSAGE_CONTEXT_ITEMS,
    max_chars: int = MAX_MESSAGE_CONTEXT_CHARS,
) -> MessageEvidenceContext:
    """Adapt a canonical timeline to a small, neutral message decision context.

    The adapter does not interpret evidence. Only observations with explicit
    provenance can cross this boundary. Absence, inference, strategy, and
    unprovenanced items are counted but never serialized into ``items``.
    """
    if max_items < 0 or max_chars < 0:
        raise ValueError("context limits must be non-negative")
    if timeline is None:
        return _empty_context()

    try:
        parsed = (
            timeline
            if isinstance(timeline, EvidenceTimeline)
            else EvidenceTimeline.model_validate(timeline)
        )
    except (ValidationError, TypeError, ValueError):
        return _empty_context(status="failed", excluded_counts={"invalid_timeline": 1})

    excluded = {
        "absence": 0,
        "inference": 0,
        "strategy": parsed.excluded_strategy_count,
        "unprovenanced_observation": 0,
        "invalid_observation": 0,
        "invalid_item": parsed.rejected_item_count,
        "item_limit": 0,
        "character_limit": 0,
    }
    candidates: list[EvidenceTimelineEntry] = []
    for entry in parsed.entries:
        if entry.epistemic_type == "absence":
            excluded["absence"] += 1
            continue
        if entry.epistemic_type == "inference":
            excluded["inference"] += 1
            continue
        valid_refs = [
            ref.strip()
            for ref in entry.provenance_refs
            if isinstance(ref, str) and ref.strip()
        ]
        if not entry.content.strip():
            excluded["invalid_observation"] += 1
            continue
        if not valid_refs:
            excluded["unprovenanced_observation"] += 1
            continue
        candidates.append(entry)

    # Stable newest-first order; the evidence ID is a deterministic tie-break.
    candidates.sort(key=lambda entry: entry.evidence_id)
    candidates.sort(key=_normalized_time, reverse=True)

    selected: list[MessageEvidenceContextItem] = []
    encoded_chars = 0
    for entry in candidates:
        if len(selected) >= max_items:
            excluded["item_limit"] += 1
            continue
        item = MessageEvidenceContextItem(
            evidence_id=entry.evidence_id,
            content=entry.content,
            source_engine=entry.source_engine,
            source_status=entry.source_status,
            timeline_at=entry.timeline_at,
            temporal_basis=entry.temporal_basis,
            observed_at=entry.observed_at,
            window_start=entry.window_start,
            window_end=entry.window_end,
            provenance_refs=[
                ref.strip()
                for ref in entry.provenance_refs
                if isinstance(ref, str) and ref.strip()
            ],
            scope=entry.scope,
        )
        item_chars = len(
            json.dumps(item.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        )
        if encoded_chars + item_chars > max_chars:
            excluded["character_limit"] += 1
            continue
        selected.append(item)
        encoded_chars += item_chars

    return MessageEvidenceContext(
        context_id=_context_id(selected),
        build_status="ready" if selected else "empty",
        items=selected,
        excluded_counts=excluded,
    )
