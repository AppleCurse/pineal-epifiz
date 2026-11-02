"""depth_analyst failures must be visible on agent_runs + evidence_chain.

Previously a depth exception was only logged as a WARNING and left no trace
DecisionEngine could see — silent gap. This contract locks the wiring.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from agent_core.agents.depth_analyst import DepthReport
from agent_core.task_executor import PinealExecutor


class DummyResult(BaseModel):
    compatibility_score: float = 0.9


class DummyCheck(BaseModel):
    confidence: float = 0.9
    is_suspicious: bool = False
    reason: str = ""


def _executor_reaching_depth() -> PinealExecutor:
    """Executor mocked far enough that the post-loop depth block always runs."""
    e = PinealExecutor()
    e.memory = MagicMock()
    e.memory.merge_evidence = AsyncMock()
    e.uncertainty = MagicMock()
    e.uncertainty.evaluate.return_value = DummyCheck()
    router = MagicMock()

    class DummyRoute:
        agents = ["human_behavior"]

    router.analyze = AsyncMock(return_value=DummyRoute())
    e.router = router
    e.injector = MagicMock()
    e.injector.fetch_active_rules.return_value = ""
    for name in e.agents:
        e.agents[name] = MagicMock()
        e.agents[name].execute = AsyncMock(return_value=DummyResult())
    return e


@pytest.mark.asyncio
async def test_depth_failure_is_recorded_on_agent_runs_and_evidence():
    executor = _executor_reaching_depth()
    depth = MagicMock()
    depth.analyze = AsyncMock(side_effect=RuntimeError("synthetic depth outage"))
    executor.agents["depth_analyst"] = depth

    status = await executor.execute_task(
        {"target_profile": {"username": "depth_fail", "bio": "x"}},
        "depth_failure_wiring",
    )

    assert "depth_analyst" in status.agent_runs
    run = status.agent_runs["depth_analyst"]
    assert run.status == "failed"
    assert run.error_code == "RuntimeError"
    assert "synthetic depth outage" in (run.error_message or "")

    failure = next(
        item for item in status.evidence_chain
        if item.get("agent") == "depth_analyst" and item.get("evidence_type") == "execution_failure"
    )
    assert failure["result"]["error_code"] == "RuntimeError"
    assert status.depth_report is not None
    assert status.depth_report.get("available") is False
    assert status.depth_report.get("reason") == "DEPTH_ANALYSIS_UNAVAILABLE"
    # DecisionEngine must see the failed run → not a silent full COMPLETED.
    assert status.status in {"partially_completed", "completed"}
    # With a failed depth run present, final status is partial.
    assert status.status == "partially_completed"


@pytest.mark.asyncio
async def test_depth_success_is_recorded_on_agent_runs():
    executor = _executor_reaching_depth()
    depth = MagicMock()
    depth.analyze = AsyncMock(
        return_value=DepthReport(
            reality_index=0.82,
            reality_rationale="synthetic ok",
            essence_one_liner="ok",
            reality_findings=[],
            quote_guard={"kept": 1, "checked": 1, "dropped_fake_quote": 0},
        )
    )
    executor.agents["depth_analyst"] = depth

    status = await executor.execute_task(
        {"target_profile": {"username": "depth_ok", "bio": "x"}},
        "depth_success_wiring",
    )

    assert "depth_analyst" in status.agent_runs
    run = status.agent_runs["depth_analyst"]
    assert run.status == "completed"
    assert run.confidence == pytest.approx(0.82)
    assert status.depth_report is not None
    assert status.depth_report.get("reality_index") == pytest.approx(0.82)
    depth.analyze.assert_awaited()


@pytest.mark.asyncio
async def test_halted_pipeline_does_not_emit_completed_or_log_success():
    from agent_core.domain.pipeline_status import PipelineStatus
    from agent_core.schemas.telemetry import TaskCompletedEvent

    executor = _executor_reaching_depth()
    executor.decision_engine.make_decision = MagicMock(return_value=PipelineStatus.HALTED_INSUFFICIENT_EVIDENCE)
    events, logs = [], []
    executor._emit = events.append
    executor._log = lambda level, message: logs.append((level, message))
    status = await executor.execute_task({"target_profile": {"bio": "x"}}, "halted_no_success")
    assert status.status == PipelineStatus.HALTED_INSUFFICIENT_EVIDENCE
    assert not any(isinstance(event, TaskCompletedEvent) for event in events)
    assert not any("TAMAMLANDI" in message for _, message in logs)


@pytest.mark.asyncio
async def test_interpreter_response_does_not_become_finished_execution():
    from agent_core.agents.interpreter_agent import InterpreterResult

    executor = _executor_reaching_depth()
    executor.router.analyze.return_value.agents = ["interpreter"]
    agent = MagicMock()
    agent.execute = AsyncMock(return_value=InterpreterResult(prompt="x", status="code_proposed", code_blocks=["print(1)"]))
    executor.agents["interpreter"] = agent
    status = await executor.execute_task({"target_profile": {"bio": "x"}}, "interpreter_no_run")
    run = status.agent_runs["interpreter"]
    assert run.status == "unavailable"
    assert run.output_summary["status"] == "code_proposed"
    assert "interpreter" not in status.completed_agents
    assert status.status != "completed"


@pytest.mark.asyncio
async def test_executor_overrules_full_status_when_a_recorded_run_failed():
    from agent_core.domain.pipeline_status import PipelineStatus
    from agent_core.schemas.telemetry import TaskCompletedEvent

    executor = _executor_reaching_depth()
    depth = MagicMock()
    depth.analyze = AsyncMock(side_effect=RuntimeError("outage"))
    executor.agents["depth_analyst"] = depth
    executor.decision_engine.make_decision = MagicMock(return_value=PipelineStatus.COMPLETED)
    events = []
    executor._emit = events.append
    status = await executor.execute_task({"target_profile": {"bio": "x"}}, "forced_full")
    assert status.agent_runs["depth_analyst"].status == "failed"
    assert status.status == PipelineStatus.PARTIALLY_COMPLETED
    assert not any(isinstance(event, TaskCompletedEvent) for event in events)


@pytest.mark.asyncio
async def test_interpreter_provider_error_is_a_failed_run():
    from agent_core.agents.interpreter_agent import InterpreterResult

    executor = _executor_reaching_depth()
    executor.router.analyze.return_value.agents = ["interpreter"]
    agent = MagicMock()
    agent.execute = AsyncMock(return_value=InterpreterResult(prompt="x", status="error", error_message="provider failed"))
    executor.agents["interpreter"] = agent
    status = await executor.execute_task({"target_profile": {"bio": "x"}}, "interpreter_failed")
    assert status.agent_runs["interpreter"].status == "failed"
    assert "interpreter" not in status.completed_agents


@pytest.mark.asyncio
async def test_resumed_legacy_runs_do_not_emit_proven_completion():
    from agent_core.domain.memory_models import AgentRun
    from agent_core.domain.pipeline_status import PipelineStatus
    from agent_core.schemas.telemetry import TaskCompletedEvent
    from agent_core.task_executor import TaskStatus

    task_id = "resume_old"
    prior = TaskStatus(
        task_id=task_id,
        status="halted_evidence",
        planned_agents=["human_behavior"],
        completed_agents=["human_behavior"],
        agent_runs={name: AgentRun(task_id=task_id, agent_name=name, status="completed")
                    for name in ("human_behavior", "depth_analyst", "shadow_executor")},
    )
    executor = _executor_reaching_depth()
    executor.decision_engine.make_decision = MagicMock(return_value=PipelineStatus.COMPLETED)
    events = []
    executor._emit = events.append
    status = await executor.execute_task({"target_profile": {"bio": "x"}}, task_id, resume_from=prior)
    assert status.status == PipelineStatus.COMPLETED
    assert status.completion_policy is None
    assert not any(isinstance(event, TaskCompletedEvent) for event in events)
