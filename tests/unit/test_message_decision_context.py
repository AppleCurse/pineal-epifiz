from datetime import datetime, timezone

import pytest

from agent_core.domain.evidence_models import EvidenceItem
from agent_core.domain.pillar_models import EvidenceStatus
from agent_core.services.evidence_timeline import build_evidence_timeline
from agent_core.services.message_decision_context import build_message_evidence_context


def _item(evidence_id: str, epistemic_type: str, content: str, at: datetime, refs=None):
    return EvidenceItem(
        evidence_id=evidence_id,
        epistemic_type=epistemic_type,
        source_engine="fixture_engine",
        source_status=EvidenceStatus.OBSERVED,
        content=content,
        provenance_refs=list(refs or []),
        scope={"fixture_scope": "controlled"},
        observed_at=at,
        source_metrics={"metric_not_for_prompt": 123},
    )


def test_message_context_is_stable_typed_and_provenance_gated():
    old = datetime(2025, 1, 1, tzinfo=timezone.utc)
    recent = datetime(2025, 1, 2, tzinfo=timezone.utc)
    timeline = build_evidence_timeline(
        [
            _item("ev_00000000000000000001", "observation", "older observation", old, ["post:1"]),
            _item("ev_00000000000000000002", "observation", "newer observation", recent, ["post:2"]),
            _item("ev_00000000000000000003", "observation", "unprovenanced observation", recent),
            _item("ev_00000000000000000004", "absence", "posting gap only", recent, ["post:4"]),
            _item("ev_00000000000000000005", "inference", "unverified interpretation", recent, ["post:5"]),
            _item("ev_00000000000000000006", "strategy", "recommendation must not cross", recent, ["post:6"]),
        ]
    )

    context = build_message_evidence_context(timeline)
    round_trip = build_message_evidence_context(timeline.model_dump(mode="json"))

    assert context == round_trip
    assert context.build_status == "ready"
    assert [item.evidence_id for item in context.items] == [
        "ev_00000000000000000002",
        "ev_00000000000000000001",
    ]
    assert context.context_id == round_trip.context_id
    assert context.excluded_counts == {
        "absence": 1,
        "inference": 1,
        "strategy": 1,
        "unprovenanced_observation": 1,
        "invalid_observation": 0,
        "invalid_item": 0,
        "item_limit": 0,
        "character_limit": 0,
    }
    serialized_items = str([item.model_dump(mode="json") for item in context.items])
    assert "unprovenanced observation" not in serialized_items
    assert "posting gap only" not in serialized_items
    assert "unverified interpretation" not in serialized_items
    assert "recommendation must not cross" not in serialized_items
    assert "metric_not_for_prompt" not in serialized_items


def test_message_context_limits_and_invalid_timeline_fail_closed():
    at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    timeline = build_evidence_timeline(
        [
            _item("ev_00000000000000000011", "observation", "first", at, ["post:11"]),
            _item("ev_00000000000000000012", "observation", "second", at, ["post:12"]),
        ]
    )

    limited = build_message_evidence_context(timeline, max_items=1)
    invalid = build_message_evidence_context({"schema_version": "wrong", "entries": []})

    assert len(limited.items) == 1
    assert limited.excluded_counts["item_limit"] == 1
    assert invalid.build_status == "failed"
    assert invalid.items == []
    assert invalid.excluded_counts == {"invalid_timeline": 1}


@pytest.mark.asyncio
async def test_pattern_interrupt_requires_valid_context_evidence_ids():
    from agent_core.agents.pattern_interrupt import GeneratedMessage, PatternInterrupt

    timeline = build_evidence_timeline(
        [
            _item(
                "ev_00000000000000000021",
                "observation",
                "source observation",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                ["post:21"],
            )
        ]
    )
    context = build_message_evidence_context(timeline).model_dump(mode="json")

    class _Gateway:
        def __init__(self, evidence_ids):
            self.evidence_ids = evidence_ids
            self.prompt = ""

        async def query_json_chain(self, prompt, _schema, **_kwargs):
            self.prompt = prompt
            return GeneratedMessage(
                message="A source-grounded draft.",
                strategy="observation",
                confidence=0.8,
                compliance_score=100.0,
                dialogue_tree=[],
                evidence_ids_used=self.evidence_ids,
            )

    missing_id_gateway = _Gateway([])
    missing_id_result = await PatternInterrupt().execute(
        {"message_evidence_context": context}, None, missing_id_gateway
    )
    assert missing_id_result.message == ""
    assert missing_id_result.fallback_reason == "canonical_message_missing_evidence_reference"
    assert missing_id_result.data_confidence is False

    valid_id_gateway = _Gateway(["ev_00000000000000000021"])
    valid_id_result = await PatternInterrupt().execute(
        {"message_evidence_context": context}, None, valid_id_gateway
    )
    assert valid_id_result.message == "A source-grounded draft."
    assert valid_id_result.evidence_ids_used == ["ev_00000000000000000021"]
    assert valid_id_result.decision_context_id == context["context_id"]
    assert "source_metrics" not in valid_id_gateway.prompt

    unsupported_id_gateway = _Gateway(["ev_ffffffffffffffffffff"])
    unsupported_id_result = await PatternInterrupt().execute(
        {"message_evidence_context": context}, None, unsupported_id_gateway
    )
    assert unsupported_id_result.message == ""
    assert unsupported_id_result.fallback_reason == "unsupported_canonical_evidence_reference"
