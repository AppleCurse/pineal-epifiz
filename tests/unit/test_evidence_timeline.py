from datetime import datetime, timezone

from agent_core.domain.evidence_models import EvidenceItem
from agent_core.domain.pillar_models import EvidenceStatus
from agent_core.services.evidence_timeline import build_evidence_timeline


T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
T1 = datetime(2024, 2, 1, tzinfo=timezone.utc)


def _item(
    evidence_id: str,
    epistemic_type: str,
    *,
    timestamp: datetime | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    content: str,
    scope: dict | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev_{evidence_id:0<20}",
        epistemic_type=epistemic_type,
        source_engine="test_engine",
        source_status=EvidenceStatus.WEAK,
        content=content,
        provenance_refs=["source:one"],
        scope=scope,
        observed_at=timestamp,
        window_start=window_start,
        window_end=window_end,
        confidence=None,
    )


def test_timeline_is_sorted_typed_sourced_and_excludes_strategy():
    observation = _item(
        "1",
        "observation",
        timestamp=T1,
        content="A source-reported event.",
    )
    absence = _item(
        "2",
        "absence",
        window_start=T0,
        window_end=T1,
        content="A topic was absent from the analyzed corpus.",
        scope={"corpus_basis": "target_profile.posts"},
    )
    inference = _item(
        "3",
        "inference",
        content="A source-generated hypothesis.",
    )
    strategy = _item(
        "4",
        "strategy",
        timestamp=T0,
        content="A recommendation that must not enter the timeline.",
    )

    timeline = build_evidence_timeline(
        [inference, strategy, observation, absence, {"agent": "raw", "core": "bypass"}]
    )

    assert timeline.schema_version == "evidence-timeline-v1"
    assert [entry.evidence_id for entry in timeline.entries] == [
        absence.evidence_id,
        observation.evidence_id,
        inference.evidence_id,
    ]
    assert timeline.excluded_strategy_count == 1
    assert timeline.rejected_item_count == 1
    assert all(entry.epistemic_type != "strategy" for entry in timeline.entries)
    assert timeline.entries[0].epistemic_note.startswith("Absence signal scoped")
    assert "not a life-event or psychological conclusion" in timeline.entries[0].epistemic_note
    assert timeline.entries[1].epistemic_note.startswith("Source-emitted observation/measurement")
    assert timeline.entries[2].epistemic_note.startswith("Unverified inference")
    assert timeline.entries[0].scope == {"corpus_basis": "target_profile.posts"}
    assert timeline.entries[0].provenance_refs == ["source:one"]
    assert timeline.source_status_note.endswith("not an independent truth/verification verdict.")


def test_timeline_uses_observed_at_before_window_and_accepts_json_items():
    item = _item(
        "5",
        "observation",
        timestamp=T0,
        window_start=T1,
        content="Source timestamp has its own semantics.",
    )

    timeline = build_evidence_timeline([item.model_dump(mode="json")])

    assert len(timeline.entries) == 1
    assert timeline.entries[0].temporal_basis == "observed_at"
    assert timeline.entries[0].timeline_at == T0


def test_empty_timeline_has_no_synthetic_entries():
    timeline = build_evidence_timeline(None)

    assert timeline.entries == []
    assert timeline.excluded_strategy_count == 0
    assert timeline.rejected_item_count == 0
