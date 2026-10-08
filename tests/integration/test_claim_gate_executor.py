from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from agent_core.agents.autonomous_verifier import (
    CanonicalObservationCheck,
    VOTE_FALSE,
    VerificationResult,
    VerifierReport,
)
from agent_core.agents.depth_analyst import DepthReport
from agent_core.agents.pattern_interrupt import GeneratedMessage
from agent_core.services.claim_decision_gate import DIRECT_REFUTATION_BASIS
from agent_core.shadow.shadow_executor import ShadowResult
from agent_core.task_executor import PinealExecutor, TaskStatus
from agent_core.services.tier2_evidence_adapter import canonicalize_tier2_output


CLAIM_ID = "clm_0123456789abcdefabcd"
CLAIM_TEXT = "Senior Strategist at Acme"


class Check(BaseModel):
    confidence: float = 0.9
    is_suspicious: bool = False
    reason: str = ""
    no_decision: bool = False


class VerifierStub:
    async def execute(self, input_data, memory, gateway):
        return VerifierReport(
            verifications=[VerificationResult(
                claim_text=CLAIM_TEXT,
                claim_id=CLAIM_ID,
                claim_origin="bio_extracted",
                claim_source_refs=["target_profile.bio"],
                truth_status=VOTE_FALSE,
                evidence_url="https://example.test/source",
                evidence_quote="The source directly denies the employer claim.",
                contradiction_detail="A quoted source says the subject never worked there.",
                juror_votes={"seat_a": VOTE_FALSE, "seat_b": VOTE_FALSE},
                vote_audit={
                    "seat_a": "kanit_kapisi_gecildi:1.0",
                    "seat_b": "kanit_kapisi_gecildi:1.0",
                },
                direct_refutation_confirmed=True,
                direct_refutation_basis=DIRECT_REFUTATION_BASIS,
            )],
            status="CONTRADICTED",
            confidence=0.9,
            data_confidence=True,
        )


class UnverifiedVerifierStub:
    async def execute(self, input_data, memory, gateway):
        return VerifierReport(
            verifications=[],
            canonical_observation_checks=[CanonicalObservationCheck(
                claim_id="clm_fedcba9876543210abcd",
                evidence_id="ev_0123456789abcdefabcd",
                source_kind="pillar_bundle",
                claim_text="A posting interval was measured.",
                source_engine="seismos_engine",
                source_status="observed",
                provenance_refs=["post:2025-01-01"],
                provenance_integrity="valid",
                source_consistency="consistent",
                reproducibility="reproduced",
                decision_note="Reproduced; no factual verdict.",
            )],
            status="UNVERIFIED",
            confidence=0.0,
            data_confidence=False,
            fallback_reason="no_bio",
        )


class PatternStub:
    async def execute(self, input_data, memory, gateway):
        return GeneratedMessage(
            message=f"I saw that you are a {CLAIM_TEXT}.",
            strategy="neutral",
            confidence=0.9,
            compliance_score=100.0,
            dialogue_tree=[],
            data_confidence=True,
            fallback_reason=None,
        )


class ShadowStub:
    async def execute(self, input_data):
        # The routed PatternInterrupt result is already filtered; this stub
        # also tests the independent final ShadowExecutor message boundary.
        assert input_data["_pattern_interrupt"]["message"] == ""
        return ShadowResult(
            message=f"Could I ask about your {CLAIM_TEXT}?",
            dark_profile={},
            strategy="neutral",
            nlp_sequence=[],
            confidence=0.9,
        )


@pytest.mark.asyncio
async def test_executor_traces_gate_and_filters_same_claim_from_messages(monkeypatch):
    monkeypatch.delenv("PINEAL_ENABLE_CANONICAL_MESSAGE_CONTEXT", raising=False)
    executor = PinealExecutor()
    executor.router.analyze = AsyncMock(return_value=type("Route", (), {
        "agents": ["autonomous_verifier", "pattern_interrupt"]
    })())
    executor.uncertainty = MagicMock()
    executor.uncertainty.evaluate.return_value = Check()
    executor.memory = MagicMock()
    executor.memory.merge_evidence = AsyncMock()
    executor.injector = MagicMock()
    executor.injector.fetch_active_rules.return_value = {}
    executor.agents["autonomous_verifier"] = VerifierStub()
    executor.agents["pattern_interrupt"] = PatternStub()
    executor.agents["shadow_executor"] = ShadowStub()
    executor.agents["depth_analyst"] = MagicMock()
    executor.agents["depth_analyst"].analyze = AsyncMock(return_value=DepthReport(
        reality_index=0.9,
        reality_rationale="",
        essence_one_liner="",
        reality_findings=[],
        contradictions=[],
    ))

    input_data = {"target_profile": {"bio": CLAIM_TEXT}}
    status = await executor.execute_task(input_data, "claim-gate-task")

    gate_record = next(
        item for item in status.evidence_chain if item["agent"] == "claim_decision_gate"
    )
    decision = gate_record["result"]["decisions"][0]
    assert decision["claim_id"] == CLAIM_ID
    assert decision["decision_state"] == "BLOCK_SAME_CLAIM"

    pattern_record = next(
        item for item in status.evidence_chain if item["agent"] == "pattern_interrupt"
    )
    assert pattern_record["result"]["message"] == ""
    assert pattern_record["claim_gate"]["claim_ids"] == [CLAIM_ID]

    assert status.shadow_profile["message"] == ""
    assert status.shadow_profile["claim_gate"]["claim_ids"] == [CLAIM_ID]
    assert input_data["verifications"]["verifications"][0]["claim_origin"] == "bio_extracted"


@pytest.mark.asyncio
async def test_executor_preserves_unverified_verifier_checks_for_depth_analyst():
    executor = PinealExecutor()
    executor.router.analyze = AsyncMock(return_value=type("Route", (), {
        "agents": ["autonomous_verifier"]
    })())
    executor.uncertainty = MagicMock()
    executor.uncertainty.evaluate.return_value = Check(confidence=0.9)
    executor.memory = MagicMock()
    executor.memory.merge_evidence = AsyncMock()
    executor.injector = MagicMock()
    executor.injector.fetch_active_rules.return_value = {}
    executor.agents["autonomous_verifier"] = UnverifiedVerifierStub()
    seen = {}

    async def capture_depth(input_data, evidence_chain):
        seen["verifications"] = input_data.get("verifications")
        return DepthReport(
            reality_index=0.9,
            reality_rationale="",
            essence_one_liner="",
            reality_findings=[],
            contradictions=[],
        )

    executor.agents["depth_analyst"] = MagicMock()
    executor.agents["depth_analyst"].analyze = AsyncMock(side_effect=capture_depth)

    status = await executor.execute_task({"target_profile": {}}, "unverified-check-task")

    assert status.agent_runs["autonomous_verifier"].status == "completed_no_decision"
    assert seen["verifications"]["fallback_reason"] == "no_bio"
    assert seen["verifications"]["canonical_observation_checks"][0]["factual_truth_status"] == "BİLİNMİYOR"
    verifier_record = next(
        item for item in status.evidence_chain if item["agent"] == "autonomous_verifier"
    )
    assert verifier_record["result"]["canonical_observation_checks"][0]["downstream_decision_state"] == "NO_FACTUAL_VERDICT"


def test_executor_adds_internal_checks_for_separately_stored_tier2_observations():
    target_analysis = {
        "data_confidence": True,
        "observations": ["Three posts mention a weekly reading group."],
        "possible_interpretations": ["The group may be important."],
        "alternative_interpretations": [],
    }
    canonical_items = canonicalize_tier2_output("human_behavior", target_analysis)
    observation = next(item for item in canonical_items if item.epistemic_type == "observation")
    status = TaskStatus(task_id="tier2-internal-check")
    status.evidence_chain.extend([
        {
            "agent": "tier2_evidence_adapter",
            "source_agent": "human_behavior",
            "evidence_type": "tier2_canonical_output",
            "result": {
                "items": [item.model_dump(mode="json") for item in canonical_items],
            },
        },
        {
            "agent": "autonomous_verifier",
            "evidence_type": "agent_output",
            "result": {"canonical_observation_checks": []},
        },
    ])
    input_data = {
        "target_analysis": target_analysis,
        "verifications": {"canonical_observation_checks": []},
    }

    PinealExecutor._refresh_internal_verification_checks(status, input_data)

    check = input_data["verifications"]["canonical_observation_checks"][0]
    assert check["evidence_id"] == observation.evidence_id
    assert check["source_kind"] == "tier2_agent_output"
    assert check["provenance_integrity"] == "missing"
    assert check["source_consistency"] == "consistent"
    assert check["reproducibility"] == "reproduced"
    assert check["factual_truth_status"] == "BİLİNMİYOR"
    assert check["downstream_decision_state"] == "NO_FACTUAL_VERDICT"
    assert status.evidence_chain[-1]["result"]["canonical_observation_checks"] == [check]
