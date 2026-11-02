"""Isolated task lifecycle projection and conservative route-completion policy.

A finished route is not evidence that a domain decision was produced.
"""

from agent_core.domain.pipeline_status import PipelineStatus

COMPLETION_POLICY = "planned_runs_v1"


def constrain_completion(result, task_id, planned_agents, runs):
    """Full route completion needs each planned run and no degraded run."""
    if result != PipelineStatus.COMPLETED:
        return result
    if not planned_agents or not runs:
        return PipelineStatus.PARTIALLY_COMPLETED
    for name in planned_agents:
        run = runs.get(name)
        if run is None or run.agent_name != name or run.task_id != task_id or run.status != "completed":
            return PipelineStatus.PARTIALLY_COMPLETED
    if any(run.status != "completed" or run.task_id != task_id or run.agent_name != name for name, run in runs.items()):
        return PipelineStatus.PARTIALLY_COMPLETED
    return result


def task_state_fields(snapshot):
    """Project the status without backfilling a decision or legacy success."""
    status = getattr(snapshot, "status", snapshot)
    status = str(getattr(status, "value", status) or "").lower()
    phase, outcome = "unknown", "unknown"
    if status in {"initialized", "processing", "running"}:
        phase = "running"
    elif status == "awaiting_authorization":
        phase = "waiting"
    elif status in {"completed", "partially_completed", "timed_out", "failed", "cancelled", "canceled"} or status.startswith("halted"):
        phase = "finished"
        if status == "partially_completed":
            outcome = "partial"
        elif status == "completed" and getattr(snapshot, "completion_policy", None) == COMPLETION_POLICY:
            outcome = "completed"
        elif status == "timed_out":
            outcome = "timed_out"
        elif status == "failed":
            outcome = "failed"
        elif status in {"cancelled", "canceled"}:
            outcome = "cancelled"
        elif status.startswith("halted"):
            outcome = "halted"
    return {"task_state_version": 1, "task_phase": phase, "task_outcome": outcome, "decision_state": "unknown"}
