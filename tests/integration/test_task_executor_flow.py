import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel
from agent_core.agents.depth_analyst import DepthReport
from agent_core.task_executor import PinealExecutor
from agent_core.domain.memory_models import TaskSnapshot

class DummyResult(BaseModel):
    compatibility_score: float = 0.9

class DummyCheck(BaseModel):
    confidence: float
    is_suspicious: bool
    reason: str = ""


def _ok_depth_report() -> DepthReport:
    return DepthReport(
        reality_index=0.9,
        reality_rationale="test",
        essence_one_liner="test",
        reality_findings=[],
        quote_guard={"kept": 0, "checked": 0, "dropped_fake_quote": 0},
    )

@pytest.fixture
def mock_router():
    router = MagicMock()
    # RoutePlan expects agents as a list
    class DummyRoute:
        agents = ["human_behavior", "mirror_truth", "resonance_calc"]
    router.analyze = AsyncMock(return_value=DummyRoute())
    return router

@pytest.fixture
def mock_uncertainty():
    uncertainty = MagicMock()
    uncertainty.evaluate.return_value = DummyCheck(confidence=0.9, is_suspicious=False)
    return uncertainty

@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.merge_evidence = AsyncMock()
    return memory

@pytest.fixture
def mock_llm_gateway():
    llm = MagicMock()
    llm.query = AsyncMock(return_value="Verified Note")
    return llm

@pytest.fixture
def mock_injector():
    injector = MagicMock()
    injector.fetch_active_rules.return_value = {"rule": "test"}
    return injector

@pytest.fixture
def executor(mock_router, mock_uncertainty, mock_memory, mock_llm_gateway, mock_injector):
    e = PinealExecutor()
    e.router = mock_router
    e.uncertainty = mock_uncertainty
    e.memory = mock_memory
    e.llm_gateway = mock_llm_gateway
    e.injector = mock_injector
    
    # Mock agents
    for name in e.agents:
        e.agents[name] = MagicMock()
        e.agents[name].execute = AsyncMock(return_value=DummyResult())
    # depth_analyst is invoked via .analyze() (not execute) after the main loop;
    # without a real DepthReport the new failure-wiring records a failed run and
    # DecisionEngine correctly marks the pipeline partially_completed.
    e.agents["depth_analyst"].analyze = AsyncMock(return_value=_ok_depth_report())

    return e

@pytest.mark.asyncio
async def test_execute_task_full_flow(executor):
    input_data = {"target_profile": {"images": ["http://test.com/1.jpg"]}}
    
    # Mock download to avoid real network
    executor._download_images = AsyncMock(return_value=["/tmp/1.jpg"])
    
    status = await executor.execute_task(input_data, "task_1")
    
    assert isinstance(status, TaskSnapshot)
    assert status.status == "completed"
    assert status.task_id == "task_1"
    # 3 rota ajanı + 7-sütun + evidence adapter + neutral timeline + depth.
    # Empty evidence and its empty timeline are both explicit chain records.
    chain_agents = [record["agent"] for record in status.evidence_chain]
    assert len(chain_agents) == 7, chain_agents
    assert chain_agents.count("psychodynamic_depth") == 1
    assert chain_agents.count("pineal_7pillar") == 1
    assert chain_agents.count("pillar_evidence_adapter") == 1
    adapter_record = next(
        record for record in status.evidence_chain
        if record["agent"] == "pillar_evidence_adapter"
    )
    assert adapter_record["result"]["build_status"] == "empty"
    assert adapter_record["result"]["item_count"] == 0
    timeline_record = next(
        record for record in status.evidence_chain
        if record["agent"] == "evidence_timeline"
    )
    assert timeline_record["result"]["build_status"] == "empty"
    assert timeline_record["result"]["entry_count"] == 0
    # [BOSS-5] Mühür yalnız kanıt zincirini saklar: 7-sütun motorlarının HAM
    # çıktısı bu kaydın içinde olmalı, yoksa "adli mühür" iddiası kapsamsız kalır.
    pillar_record = next(r for r in status.evidence_chain if r["agent"] == "pineal_7pillar")
    pillars = pillar_record["result"]["pillars"]
    for name in ("frequency_map", "seismos_events", "void_map", "strata_map",
                 "gravity_map", "pulse_map", "key_matrix"):
        assert pillars[name] is not None, f"{name} mühürde yok"
    assert pillars["version"] == "pillar-full-v1"
    
    # Ensure memory was updated
    executor.memory.merge_evidence.assert_called_once()
    
    # Ensure route was analyzed
    executor.router.analyze.assert_called_once()

@pytest.mark.asyncio
async def test_execute_task_halt_low_confidence(executor):
    input_data = {}
    
    # Simulate low confidence on first agent
    executor.uncertainty.evaluate.return_value = DummyCheck(confidence=0.4, is_suspicious=False)
    
    status = await executor.execute_task(input_data, "task_2")
    
    assert status.status == "halted_evidence"
    # Raw pillar plus canonical-evidence and neutral-timeline records.
    assert len(status.evidence_chain) == 3
    
@pytest.mark.asyncio
async def test_execute_task_suspicious_research(executor):
    input_data = {}
    
    # Override router to only return a simple agent that doesn't expect specific fields on result
    class SimpleRoute:
        agents = ["human_behavior"]
    executor.router.analyze = AsyncMock(return_value=SimpleRoute())
    
    # First agent suspicious, deep research needed
    executor.uncertainty.evaluate.return_value = DummyCheck(confidence=0.8, is_suspicious=True, reason="Inconsistent")
    
    status = await executor.execute_task(input_data, "task_3")
    
    # The research note is separate evidence; it must not replace the typed
    # human_behavior output that downstream agents consume.
    assert status.status == "completed"
    executor.llm_gateway.query.assert_called() # Deep research called
    assert input_data["target_analysis"]["compatibility_score"] == 0.9
    original = next(item for item in status.evidence_chain if item["agent"] == "human_behavior")
    research = next(item for item in status.evidence_chain if item["agent"] == "deep_research")
    assert original["evidence_type"] == "agent_output"
    assert original["uncertainty"]["reason"] == "Inconsistent"
    assert research["evidence_type"] == "verification_note"
    assert research["source_agent"] == "human_behavior"

@pytest.mark.asyncio
async def test_execute_task_frequency_mismatch(executor):
    input_data = {}
    
    # Make resonance calculator return low compatibility
    executor.agents["resonance_calc"].execute = AsyncMock(return_value=DummyResult(compatibility_score=0.5))
    
    status = await executor.execute_task(input_data, "task_4")
    
    assert status.status == "halted_frequency"
    # Three routed outputs plus raw pillar, canonical evidence, and timeline.
    assert len(status.evidence_chain) == 6


@pytest.mark.asyncio
async def test_executor_carries_typed_pillar_evidence_before_router(executor, monkeypatch):
    from datetime import datetime, timezone

    from agent_core.domain.pillar_models import (
        EvidenceStatus,
        SeismicEvent,
        SeismicKind,
        SeismosReport,
    )
    from agent_core.domain.pillar_wave2_models import FullPillarBundle, KeyReport
    from agent_core.engines.pillar_orchestrator import PillarOrchestrator
    from agent_core.services.cognitive_router import RoutePlan

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 2, 1, tzinfo=timezone.utc)
    bundle = FullPillarBundle(
        seismos=SeismosReport(events=[SeismicEvent(
            event_id="sez_executor_case",
            kind=SeismicKind.SILENCE_GAP,
            intensity=7.0,
            timestamp=start,
            window_start=start,
            window_end=end,
            observables=["Observed gap between two timestamped posts."],
            metrics={"gap_hours": 744.0},
            hypotheses=["A missing-data explanation remains possible."],
            status=EvidenceStatus.OBSERVED,
            evidence_refs=["post:2024-01-01", "post:2024-02-01"],
        )]),
        key=KeyReport(
            status=EvidenceStatus.WEAK,
            gate_key="Heuristic suggestion only.",
            confidence=1 / 6,
            evidence_refs=["key:synthesized"],
        ),
    )

    async def _pillar_run(_self, _data):
        return bundle.as_snapshot_fields()

    monkeypatch.setattr(PillarOrchestrator, "run", _pillar_run)
    captured = {}

    async def _route(data):
        captured["items"] = data.get("forensic_evidence")
        captured["upstream"] = data.get("_upstream_findings")
        captured["timeline"] = data.get("evidence_timeline")
        captured["timeline_status"] = data.get("evidence_timeline_status")
        return RoutePlan(agents=[], reasoning="test route", priority=2)

    executor.router.analyze = AsyncMock(side_effect=_route)
    input_data = {
        # Caller-supplied evidence is not trusted; the executor rebuilds it
        # from the typed bundle before routing.
        "forensic_evidence": [{"epistemic_type": "observation", "content": "spoof"}],
        "forensic_evidence_status": "ready",
        "_upstream_findings": [
            {
                "agent": "mirror_truth",
                "core": "caller-supplied bypass",
                "epistemic_type": "inference",
                "verification_status": "unverified",
                "origin": "task_executor",
            }
        ],
        "target_profile": {
            "platform": "test",
            "bio": "A small test bio.",
            "posts": [
                {"text": "First post.", "created_at": "2024-01-01T00:00:00Z"},
                {"text": "Second post.", "created_at": "2024-02-01T00:00:00Z"},
            ],
        }
    }

    status = await executor.execute_task(input_data, "task_evidence_handoff")

    items = captured["items"]
    assert items is input_data["forensic_evidence"]
    assert captured["upstream"] == []
    assert input_data["forensic_evidence_status"] == "ready"
    assert captured["timeline_status"] == "ready"
    timeline = captured["timeline"]
    assert timeline == input_data["evidence_timeline"]
    timeline_entries = timeline["entries"]
    assert all(entry["epistemic_type"] != "strategy" for entry in timeline_entries)
    assert any(entry["epistemic_type"] == "observation" for entry in timeline_entries)
    assert any(entry["epistemic_type"] == "inference" for entry in timeline_entries)
    assert timeline["source_status_note"].endswith("not an independent truth/verification verdict.")
    assert all(item["content"] != "spoof" for item in items)
    assert all(entry["content"] != "Heuristic suggestion only." for entry in timeline_entries)
    assert any(
        item["epistemic_type"] == "observation"
        and item["content"] == "Observed gap between two timestamped posts."
        for item in items
    )
    assert any(
        item["epistemic_type"] == "inference"
        and item["content"] == "A missing-data explanation remains possible."
        for item in items
    )
    assert any(
        item["epistemic_type"] == "strategy"
        and item["content"] == "Heuristic suggestion only."
        for item in items
    )
    adapter_record = next(
        item for item in status.evidence_chain
        if item["agent"] == "pillar_evidence_adapter"
    )
    assert adapter_record["evidence_type"] == "canonical_evidence"
    assert adapter_record["result"]["item_count"] == len(items)
    timeline_record = next(
        item for item in status.evidence_chain
        if item["agent"] == "evidence_timeline"
    )
    assert timeline_record["evidence_type"] == "neutral_timeline"
    assert timeline_record["result"]["excluded_strategy_count"] == 1
    assert timeline_record["result"]["entry_count"] == len(timeline_entries)
    assert all(
        entry["epistemic_type"] != "strategy"
        for entry in timeline_record["result"]["entries"]
    )


@pytest.mark.asyncio
async def test_executor_fails_closed_on_invalid_canonical_bundle(executor, monkeypatch):
    from agent_core.engines.pillar_orchestrator import PillarOrchestrator
    from agent_core.services.cognitive_router import RoutePlan

    async def _pillar_run(_self, _data):
        return {"pillar_bundle": {"unexpected": "rejected source value"}}

    monkeypatch.setattr(PillarOrchestrator, "run", _pillar_run)
    captured = {}

    async def _route(data):
        captured["items"] = data.get("forensic_evidence")
        captured["status"] = data.get("forensic_evidence_status")
        captured["timeline_status"] = data.get("evidence_timeline_status")
        return RoutePlan(agents=[], reasoning="test route", priority=2)

    executor.router.analyze = AsyncMock(side_effect=_route)
    input_data = {"target_profile": {"platform": "test"}}

    status = await executor.execute_task(input_data, "task_invalid_evidence")

    assert captured["items"] == []
    assert captured["status"] == "failed"
    assert captured["timeline_status"] == "unavailable"
    timeline_record = next(
        item for item in status.evidence_chain
        if item["agent"] == "evidence_timeline"
    )
    assert timeline_record["evidence_type"] == "not_built"
    assert timeline_record["result"]["reason_code"] == "CANONICAL_EVIDENCE_UNAVAILABLE"
    record = next(
        item for item in status.evidence_chain
        if item["agent"] == "pillar_evidence_adapter"
    )
    assert record["evidence_type"] == "execution_failure"
    assert record["result"]["error_code"] == "EVIDENCE_ADAPTER_FAILED"
    assert "rejected source value" not in record["result"]["error_message"]


@pytest.mark.asyncio
async def test_b6_controlled_message_handoff_impact_and_trace(executor, monkeypatch):
    import copy
    import re

    from agent_core.agents.pattern_interrupt import GeneratedMessage, PatternInterrupt
    from agent_core.services.cognitive_router import RoutePlan
    from agent_core.services.evidence_timeline import build_evidence_timeline
    from agent_core.services.message_decision_context import build_message_evidence_context
    from agent_core.services.pillar_evidence_adapter import adapt_pillar_bundle
    from tests.test_pillar_engines import data as pillar_fixture

    class _DeterministicGateway:
        def __init__(self):
            self.prompts = []

        async def query_json_chain(self, prompt, _schema, **_kwargs):
            self.prompts.append(prompt)
            if "CANONICAL OBSERVATION CONTEXT" in prompt:
                ids = re.findall(r'"evidence_id":\s*"(ev_[0-9a-f]{20})"', prompt)
                assert ids, "treatment received no canonical evidence IDs"
                return GeneratedMessage(
                    message="Treatment: canonical observation context supplied.",
                    strategy="observation",
                    confidence=0.8,
                    compliance_score=100.0,
                    dialogue_tree=[],
                    evidence_ids_used=[ids[0]],
                )
            return GeneratedMessage(
                message="Control: no canonical message context supplied.",
                strategy="observation",
                confidence=0.8,
                compliance_score=100.0,
                dialogue_tree=[],
            )

    gateway = _DeterministicGateway()
    executor.llm_gateway = gateway
    executor.agents["pattern_interrupt"] = PatternInterrupt()
    executor.router.analyze = AsyncMock(
        return_value=RoutePlan(agents=["pattern_interrupt"], reasoning="B6 fixture", priority=2)
    )

    fixture = pillar_fixture()
    base_input = {
        "target_profile": fixture["target_profile"],
        "target_analysis": {"evidence_quotes": ["LEGACY_TARGET_ANALYSIS_SENTINEL"]},
        "user_mirror": {},
    }

    monkeypatch.delenv("PINEAL_ENABLE_CANONICAL_MESSAGE_CONTEXT", raising=False)
    control_input = copy.deepcopy(base_input)
    control = await executor.execute_task(control_input, "task_b6_control")

    monkeypatch.setenv("PINEAL_ENABLE_CANONICAL_MESSAGE_CONTEXT", "true")
    treatment_input = copy.deepcopy(base_input)
    treatment = await executor.execute_task(treatment_input, "task_b6_treatment")

    control_record = next(
        record for record in control.evidence_chain if record.get("agent") == "pattern_interrupt"
    )
    treatment_record = next(
        record for record in treatment.evidence_chain if record.get("agent") == "pattern_interrupt"
    )
    context_record = next(
        record
        for record in treatment.evidence_chain
        if record.get("agent") == "message_decision_context_adapter"
    )
    canonical_items = adapt_pillar_bundle(
        treatment.pillar_bundle,
        target_profile=fixture["target_profile"],
    )
    timeline = build_evidence_timeline(canonical_items)
    expected_context = build_message_evidence_context(timeline)
    control_prompt, treatment_prompt = gateway.prompts

    # Reachable: the same fixture and gateway are used, and only B receives
    # the adapter-rendered canonical observation context.
    assert "CANONICAL OBSERVATION CONTEXT" not in control_prompt
    assert "CANONICAL OBSERVATION CONTEXT" in treatment_prompt
    assert "LEGACY_TARGET_ANALYSIS_SENTINEL" in control_prompt
    assert "LEGACY_TARGET_ANALYSIS_SENTINEL" not in treatment_prompt
    assert expected_context.items
    assert expected_context.items[0].evidence_id in treatment_prompt
    assert expected_context.items[0].content in treatment_prompt

    # Used + behavior delta: the deterministic model stub makes its output
    # depend only on whether the treatment context is reachable; this is not
    # a subjective message-quality score.
    assert control_record["result"]["message"] != treatment_record["result"]["message"]
    assert control_record["result"]["evidence_ids_used"] == []
    assert treatment_record["result"]["evidence_ids_used"] == [
        expected_context.items[0].evidence_id
    ]

    # Safe: the treatment prompt carries only selected observation IDs and
    # excludes absence, inference, strategy, and unprovenanced items.
    assert expected_context.excluded_counts["absence"] > 0
    assert expected_context.excluded_counts["inference"] > 0
    assert expected_context.excluded_counts["strategy"] > 0
    assert all(item.epistemic_type == "observation" for item in expected_context.items)
    absence_contents = [
        entry.content for entry in timeline.entries if entry.epistemic_type == "absence"
    ]
    inference_contents = [
        entry.content for entry in timeline.entries if entry.epistemic_type == "inference"
    ]
    strategy_items = [item for item in canonical_items if item.epistemic_type == "strategy"]
    assert absence_contents and inference_contents and strategy_items
    assert all(content not in treatment_prompt for content in absence_contents)
    assert all(content not in treatment_prompt for content in inference_contents)
    assert all(item.content not in treatment_prompt for item in strategy_items)
    assert all(content not in treatment_record["result"]["message"] for content in absence_contents)
    assert all(content not in treatment_record["result"]["message"] for content in inference_contents)
    assert all(item.content not in treatment_record["result"]["message"] for item in strategy_items)
    selected_ids = {item.evidence_id for item in expected_context.items}
    excluded_ids = {
        entry.evidence_id
        for entry in timeline.entries
        if entry.epistemic_type != "observation"
        or not entry.provenance_refs
        or entry.evidence_id not in selected_ids
    }
    assert all(evidence_id not in treatment_prompt for evidence_id in excluded_ids)
    assert "LEGACY_TARGET_ANALYSIS_SENTINEL" not in treatment_prompt

    # Traceable: adapter and message result carry the same stable context ID,
    # and the message's cited evidence is a selected adapter item.
    assert context_record["result"]["build_status"] == "ready"
    assert context_record["result"]["context_id"] == expected_context.context_id
    assert context_record["result"]["selected_evidence_ids"] == [
        item.evidence_id for item in expected_context.items
    ]
    assert treatment_record["result"]["decision_context_id"] == expected_context.context_id
    assert treatment_input.get("message_evidence_context") is None
    assert treatment_input["_pattern_interrupt"]["evidence_ids_used"] == [
        expected_context.items[0].evidence_id
    ]


@pytest.mark.asyncio
async def test_executor_records_tier2_allowlist_without_expanding_b6_timeline(
    executor, monkeypatch
):
    from agent_core.agents.human_behavior import DigitalColdReading
    from agent_core.services.cognitive_router import RoutePlan
    from tests.test_pillar_engines import data as pillar_fixture

    monkeypatch.delenv("PINEAL_ENABLE_CANONICAL_MESSAGE_CONTEXT", raising=False)
    executor.router.analyze = AsyncMock(
        return_value=RoutePlan(
            agents=["human_behavior"], reasoning="B7 allowlist fixture", priority=2
        )
    )
    executor.agents["human_behavior"].execute = AsyncMock(
        return_value=DigitalColdReading(
            observations=["B7_INTEGRATION_OBSERVATION"],
            possible_interpretations=["B7_INTEGRATION_INFERENCE"],
            alternative_interpretations=[],
            unsupported_claims=["B7_INTEGRATION_UNSUPPORTED"],
            micro_signals=[],
            confidence=0.97,
            achilles_score=50.0,
            resonance_potential=0.6,
            data_confidence=True,
        )
    )
    executor._calculate_authentic_vector = AsyncMock(return_value=None)

    fixture = pillar_fixture()
    input_data = {"target_profile": fixture["target_profile"]}
    status = await executor.execute_task(input_data, "task_b7_tier2")

    canonical_record = next(
        record
        for record in status.evidence_chain
        if record.get("agent") == "tier2_evidence_adapter"
    )
    canonical_items = canonical_record["result"]["items"]
    assert canonical_record["source_agent"] == "human_behavior"
    assert [(item["epistemic_type"], item["content"]) for item in canonical_items] == [
        ("observation", "B7_INTEGRATION_OBSERVATION"),
        ("inference", "B7_INTEGRATION_INFERENCE"),
    ]
    assert all(item["source_status"] is None for item in canonical_items)
    assert all(item["confidence"] is None for item in canonical_items)
    assert all(item["provenance_refs"] == [] for item in canonical_items)

    # B7 records these fields separately; it does not smuggle them into the
    # existing pillar-only forensic carrier or widen the B6 message timeline.
    assert all(
        "B7_INTEGRATION_" not in str(item)
        for item in input_data["forensic_evidence"]
    )
    assert all(
        "B7_INTEGRATION_" not in str(item)
        for item in input_data["evidence_timeline"]["entries"]
    )
    assert input_data.get("message_evidence_context") is None
