"""Completion policy and legacy task state remain evidence-bounded."""
from types import SimpleNamespace

import pytest

from agent_core.domain.memory_models import AgentRun, TaskSnapshot
from agent_core.domain.pipeline_status import PipelineStatus


def _run(name, status="completed", task_id="t"):
    return AgentRun(task_id=task_id, agent_name=name, status=status)


def test_full_completion_requires_all_planned_runs_and_no_degraded_run():
    from agent_core.domain.task_execution_state import constrain_completion

    runs = {"a": _run("a")}
    assert constrain_completion(PipelineStatus.COMPLETED, "t", ["a"], runs) == PipelineStatus.COMPLETED
    assert constrain_completion(PipelineStatus.COMPLETED, "t", ["a", "b"], runs) == PipelineStatus.PARTIALLY_COMPLETED
    assert constrain_completion(PipelineStatus.COMPLETED, "t", [], runs) == PipelineStatus.PARTIALLY_COMPLETED
    runs["b"] = _run("b", "timed_out")
    assert constrain_completion(PipelineStatus.COMPLETED, "t", ["a"], runs) == PipelineStatus.PARTIALLY_COMPLETED
    assert constrain_completion(PipelineStatus.COMPLETED, "t", ["a"], {"a": _run("a", task_id="other")}) == PipelineStatus.PARTIALLY_COMPLETED
    assert constrain_completion(PipelineStatus.HALTED_INSUFFICIENT_EVIDENCE, "t", ["a"], runs) == PipelineStatus.HALTED_INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("status,phase,outcome", [
    ("processing", "running", "unknown"),
    ("timed_out", "finished", "timed_out"),
    ("partially_completed", "finished", "partial"),
    ("completed", "finished", "unknown"),
    ("halted_critical", "finished", "halted"),
])
def test_legacy_state_never_invents_decision_or_full_outcome(status, phase, outcome):
    from agent_core.domain.task_execution_state import task_state_fields

    fields = task_state_fields(SimpleNamespace(status=status))
    assert fields == {"task_state_version": 1, "task_phase": phase, "task_outcome": outcome, "decision_state": "unknown"}


def test_only_policy_marked_new_completion_has_full_outcome():
    from agent_core.domain.task_execution_state import task_state_fields

    old = TaskSnapshot(task_id="t", status="completed")
    assert task_state_fields(old)["task_outcome"] == "unknown"
    marked = TaskSnapshot(task_id="t", status="completed", completion_policy="planned_runs_v1")
    assert task_state_fields(marked)["task_outcome"] == "completed"
