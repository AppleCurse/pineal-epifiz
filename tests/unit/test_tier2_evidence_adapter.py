from agent_core.agents.human_behavior import DigitalColdReading
from agent_core.agents.resonance_calculator import ResonanceProfile
from agent_core.domain.evidence_models import EvidenceItem
from agent_core.domain.pillar_models import EvidenceStatus
from agent_core.services.evidence_timeline import build_evidence_timeline
from agent_core.services.message_decision_context import build_message_evidence_context
from agent_core.services.tier2_evidence_adapter import canonicalize_tier2_output


def _human_result(*, data_confidence=True):
    return DigitalColdReading(
        observations=["B7_OBSERVED_BEHAVIOR"],
        possible_interpretations=["B7_POSSIBLE_INTERPRETATION"],
        alternative_interpretations=["B7_ALTERNATIVE_INTERPRETATION"],
        unsupported_claims=["B7_UNSUPPORTED_CLAIM"],
        micro_signals=[
            {
                "signal_type": "insomnia_isolation",
                "confidence": 0.91,
                "location": "temporal_post_distribution",
                "evidence": "B7_MIXED_HEURISTIC_SIGNAL",
                "psychological_weight": 0.75,
            }
        ],
        confidence=0.99,
        achilles_score=80.0,
        resonance_potential=0.8,
        data_confidence=data_confidence,
    )


def test_allowlisted_human_fields_keep_type_but_not_invented_provenance():
    result = _human_result()
    items = canonicalize_tier2_output("human_behavior", result)
    repeated = canonicalize_tier2_output("human_behavior", result.model_dump(mode="json"))

    assert items == repeated
    assert [(item.epistemic_type, item.content) for item in items] == [
        ("observation", "B7_OBSERVED_BEHAVIOR"),
        ("inference", "B7_POSSIBLE_INTERPRETATION"),
        ("inference", "B7_ALTERNATIVE_INTERPRETATION"),
    ]
    assert len({item.evidence_id for item in items}) == len(items)
    assert all(item.source_status is None for item in items)
    assert all(item.confidence is None for item in items)
    assert all(item.provenance_refs == [] for item in items)
    assert all(item.scope["item_provenance"] == "not_provided_by_agent_output" for item in items)
    assert "B7_UNSUPPORTED_CLAIM" not in {item.content for item in items}
    assert "B7_MIXED_HEURISTIC_SIGNAL" not in {item.content for item in items}
    # An unreferenced agent observation stays out of the B6 message context.
    timeline = build_evidence_timeline(items)
    context = build_message_evidence_context(timeline)
    assert context.items == []
    assert context.excluded_counts["unprovenanced_observation"] == 1


def test_recommendation_is_strategy_and_ambiguous_outputs_remain_untyped():
    recommendation = "Use the shared topic only if both people choose to continue."
    result = ResonanceProfile(
        state="inference_gap",
        compatibility_score=0.62,
        data_confidence=True,
        rationale="A structured test rationale.",
        recommended_approach=recommendation,
    )

    strategy_items = canonicalize_tier2_output("resonance_calc", result)
    ambiguous_depth = canonicalize_tier2_output(
        "depth_analyst",
        {
            "reality_rationale": "B7_AMBIGUOUS_LEGACY_TEXT",
            "essence_one_liner": "B7_AMBIGUOUS_LEGACY_TEXT",
        },
    )
    untrusted_result = canonicalize_tier2_output(
        "human_behavior", _human_result(data_confidence=False)
    )
    unknown_agent = canonicalize_tier2_output(
        "unknown_agent", {"observations": ["must stay untyped"]}
    )

    assert len(strategy_items) == 1
    assert strategy_items[0].epistemic_type == "strategy"
    assert strategy_items[0].content == recommendation
    assert strategy_items[0].source_status is None
    assert strategy_items[0].confidence is None
    assert strategy_items[0].provenance_refs == []
    assert strategy_items[0].scope["not_factual_evidence"] is True
    assert ambiguous_depth == []
    assert untrusted_result == []
    assert unknown_agent == []


def test_tier2_item_has_source_status_none_without_breaking_native_status():
    item = EvidenceItem(
        evidence_id="ev_1234567890abcdef1234",
        epistemic_type="observation",
        source_engine="human_behavior",
        content="Agent-labeled observation; source link unavailable.",
        scope={
            "canonicalization": "tier2-evidence-adapter-v1",
            "epistemic_note": "Agent-labeled observation; not independently verified or source-linked.",
        },
    )
    timeline = build_evidence_timeline([item])

    assert item.source_status is None
    assert timeline.entries[0].source_status is None
    assert timeline.entries[0].epistemic_note == item.scope["epistemic_note"]
    assert timeline.source_status_note.endswith(
        "not an independent truth/verification verdict."
    )
    # Native pillar statuses remain intact when present.
    native = item.model_copy(update={"source_status": EvidenceStatus.OBSERVED})
    assert native.source_status is EvidenceStatus.OBSERVED
