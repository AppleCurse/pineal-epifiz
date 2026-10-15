import pytest
from unittest.mock import AsyncMock

from agent_core.agents.autonomous_verifier import VerifierReport
from agent_core.agents.mirror_truth import MirrorOfTruth, MirrorReflection
from agent_core.agents.resonance_synthesizer import ResonanceSynthesizerAgent
from agent_core.agents.target_psyche_profiler import TargetPsycheProfiler
from agent_core.domain.memory_models import (
    AgentRun,
    AuthenticBridge,
    CognitiveStyle,
    FrictionProfile,
    PassionProfile,
)
from agent_core.services.confidence import normalize_confidence
from agent_core.services.uncertainty_engine import UncertaintyEngine
from agent_core.task_executor import PinealExecutor


class _SchemaGateway:
    def __init__(self, result):
        self.result = result
        self.query_json_chain = AsyncMock(return_value=result)


def test_confidence_normalizer_rejects_nonfinite_out_of_range_and_boolean_values():
    assert normalize_confidence(0.2) == (0.2, True)
    for value in (float("nan"), float("inf"), -0.1, 1.01, True, 10**400):
        score, valid = normalize_confidence(value)
        assert score == 0.0
        assert valid is False


def test_uninitialized_verifier_report_does_not_claim_decision_evidence():
    report = VerifierReport()
    assert report.confidence == 0.0
    assert report.data_confidence is False


@pytest.mark.asyncio
async def test_target_profiler_preserves_low_model_confidence_and_no_friction_is_empty():
    payload = {"target_profile": {"bio": "Sağlanan profil metni.", "posts": ["Bir paylaşım."]}}

    passion_gateway = _SchemaGateway(PassionProfile(
        core_passions=["müzik"], confidence=0.2,
    ))
    passion = await TargetPsycheProfiler(passion_gateway).profile_passions(payload)
    assert passion.confidence == 0.2
    assert passion.data_confidence is True

    friction_gateway = _SchemaGateway(FrictionProfile(confidence=0.2))
    frictions = await TargetPsycheProfiler(friction_gateway).profile_frictions(payload)
    assert frictions.confidence == 0.0
    assert frictions.data_confidence is False
    assert frictions.boundary_signals == []
    assert frictions.fallback_reason == "insufficient_grounded_evidence"

    cognitive_gateway = _SchemaGateway(CognitiveStyle(
        communication_tone="analitik", confidence=0.2,
    ))
    style = await TargetPsycheProfiler(cognitive_gateway).profile_cognitive(payload)
    assert style.confidence == 0.2
    assert style.data_confidence is True


@pytest.mark.asyncio
async def test_profiler_rejects_nonfinite_model_confidence_without_erasing_findings():
    result = PassionProfile(core_passions=["müzik"], confidence=0.2).model_copy(
        update={"confidence": float("nan")}
    )
    gateway = _SchemaGateway(result)
    output = await TargetPsycheProfiler(gateway).profile_passions({
        "target_profile": {"bio": "Açık metin."}
    })
    assert output.core_passions == ["müzik"]
    assert output.confidence == 0.0
    assert output.data_confidence is False
    assert output.fallback_reason == "invalid_model_confidence"


def test_uncertainty_engine_fails_closed_on_truthy_non_boolean_data_confidence():
    result = PassionProfile(core_passions=["müzik"], confidence=0.9).model_copy(
        update={"data_confidence": "false"}
    )
    report = UncertaintyEngine().evaluate(result, "passion_mapper")
    assert report.is_suspicious is True
    assert report.confidence == 0.0
    assert "Kaynak verisi" in report.reason


def test_uncertainty_engine_fails_closed_on_nan_model_confidence():
    result = PassionProfile(core_passions=["müzik"], confidence=0.5).model_copy(
        update={"confidence": float("nan"), "data_confidence": True}
    )
    report = UncertaintyEngine().evaluate(result, "passion_mapper")
    assert report.is_suspicious is True
    assert report.confidence == 0.0
    assert "geçersiz" in report.reason


def test_holistic_confidence_ignores_invalid_values_not_other_measured_runs():
    runs = {
        "passion_mapper": AgentRun(task_id="x", agent_name="passion_mapper", status="completed", confidence=0.4),
        "friction_detector": AgentRun(task_id="x", agent_name="friction_detector", status="completed", confidence=0.6),
        "cognitive_profiler": AgentRun(task_id="x", agent_name="cognitive_profiler", status="completed", confidence=0.5).model_copy(
            update={"confidence": float("nan")}
        ),
    }
    assert PinealExecutor._holistic_confidence(runs) == 0.5


@pytest.mark.asyncio
async def test_resonance_and_mirror_do_not_raise_confidence_to_a_floor():
    resonance_gateway = _SchemaGateway(AuthenticBridge(
        shared_passions=["fotoğraf"],
        suggested_opening_message="Merhaba",
        confidence=0.2,
    ))
    resonance = await ResonanceSynthesizerAgent(resonance_gateway).execute({
        "user_context": {"rituals": ["okuma"]},
        "passions": {"core_passions": ["fotoğraf"]},
        "frictions": {"sensitivities": ["kalabalık"]},
        "cognitive": {"communication_tone": "samimi"},
    })
    assert resonance.confidence == 0.2

    mirror_gateway = _SchemaGateway(MirrorReflection(
        user_core_frequency="okuma",
        surface_persona="meraklı",
        alignment_score=0.8,
        authentic_anchors=["okuma"],
        confidence=0.2,
    ))
    mirror = await MirrorOfTruth(mirror_gateway).execute({
        "user_profile": {"private_rituals": ["okuma"]},
    })
    assert mirror.confidence == 0.2
    assert mirror.data_confidence is True
