import asyncio

import pytest

from agent_core.domain.memory_models import TaskSnapshot
from agent_core.schemas.telemetry import (
    ErrorHaltEvent,
    Severity,
    StepCompletedEvent,
    TaskCompletedEvent,
    TaskStartedEvent,
)
from agent_core.services.task_lifecycle import LifecycleState, TaskLifecycleRegistry
from backend import api


def _started(task_id="task_1"):
    return TaskStartedEvent(
        task_id=task_id,
        agent_name="executor",
        input_summary="input",
    )


def _step(index, task_id="task_1"):
    return StepCompletedEvent(
        task_id=task_id,
        agent_name="agent",
        step_name=f"step_{index}",
        output_hash=f"hash_{index}",
    )


def test_event_envelope_has_immutable_run_id_and_monotonic_sequence():
    lifecycle = TaskLifecycleRegistry()

    decisions = [lifecycle.record_event(_started())] + [
        lifecycle.record_event(_step(index)) for index in range(1, 51)
    ]
    envelopes = [decision.envelope for decision in decisions]

    assert all(decision.accepted for decision in decisions)
    assert [envelope.sequence for envelope in envelopes] == list(range(1, 52))
    assert len({envelope.run_id for envelope in envelopes}) == 1
    assert all(envelope.task_id == "task_1" for envelope in envelopes)
    assert all(envelope.event_type == envelope.event.event_type for envelope in envelopes)
    assert all(envelope.timestamp.tzinfo is not None for envelope in envelopes)


def test_duplicate_event_is_rejected_without_consuming_sequence():
    lifecycle = TaskLifecycleRegistry()
    event = _started()

    first = lifecycle.record_event(event)
    duplicate = lifecycle.record_event(event.model_copy(deep=True))
    next_event = lifecycle.record_event(_step(1))

    assert first.envelope.sequence == 1
    assert duplicate.accepted is False
    assert duplicate.outcome == "DUPLICATE"
    assert next_event.envelope.sequence == 2
    assert lifecycle.metrics()["duplicate_events"] == 1


def test_terminal_event_blocks_later_event_and_state_mutation():
    lifecycle = TaskLifecycleRegistry()
    lifecycle.record_event(_started())
    terminal = lifecycle.record_event(ErrorHaltEvent(
        task_id="task_1",
        agent_name="agent",
        error_code="HALT",
        error_message="stopped",
        severity=Severity.Critical,
    ))

    late_event = lifecycle.record_event(_step(2))
    late_transition = lifecycle.transition("task_1", "processing")

    assert terminal.accepted is True
    assert terminal.state == LifecycleState.HALTED
    assert late_event.accepted is False
    assert late_event.outcome == "TERMINAL_STATE"
    assert late_transition.accepted is False
    assert lifecycle.get_run("task_1")["state"] == "HALTED"
    assert lifecycle.metrics()["rejected_terminal_events"] == 1
    assert lifecycle.metrics()["rejected_terminal_mutations"] == 1


def test_terminal_snapshot_then_completion_event_is_allowed_once():
    lifecycle = TaskLifecycleRegistry()
    snapshot = TaskSnapshot(task_id="task_1", status="completed")

    assert lifecycle.accept_snapshot(snapshot).accepted is True
    completion = TaskCompletedEvent(
        task_id="task_1",
        agent_name="executor",
        final_result_hash="abc",
        duration_ms=12,
    )
    first = lifecycle.record_event(completion)
    duplicate = lifecycle.record_event(completion.model_copy(deep=True))

    assert first.accepted is True
    assert first.envelope.sequence == 1
    assert duplicate.accepted is False
    assert duplicate.outcome == "DUPLICATE"


def test_terminal_snapshot_is_frozen_after_first_value():
    lifecycle = TaskLifecycleRegistry()
    terminal = TaskSnapshot(task_id="task_1", status="halted_critical", halted_reason="first")
    mutated = terminal.model_copy(update={"halted_reason": "changed after terminal"})

    first = lifecycle.accept_snapshot(terminal)
    same = lifecycle.accept_snapshot(terminal.model_copy(deep=True))
    rejected = lifecycle.accept_snapshot(mutated)

    assert first.accepted is True
    assert same.accepted is True
    assert same.outcome == "IDEMPOTENT"
    assert rejected.accepted is False
    assert rejected.outcome == "TERMINAL_STATE"


def test_halt_and_cancel_are_idempotent_and_cannot_replace_each_other():
    halted = TaskLifecycleRegistry()
    first_halt = halted.terminate("halted_task", "halt")
    second_halt = halted.terminate("halted_task", "halt")
    cancel_after_halt = halted.terminate("halted_task", "cancel")

    cancelled = TaskLifecycleRegistry()
    first_cancel = cancelled.terminate("cancelled_task", "cancel")
    second_cancel = cancelled.terminate("cancelled_task", "cancel")

    assert first_halt.outcome == "TRANSITIONED"
    assert second_halt.outcome == "IDEMPOTENT"
    assert cancel_after_halt.accepted is False
    assert halted.get_run("halted_task")["state"] == "HALTED"
    assert first_cancel.outcome == "TRANSITIONED"
    assert second_cancel.outcome == "IDEMPOTENT"
    assert cancelled.get_run("cancelled_task")["state"] == "CANCELLED"


def test_queue_overflow_enters_visible_degraded_mode_and_counts_dropped_event(monkeypatch):
    client_id = "overflow_test"
    room = {
        "queue": asyncio.Queue(maxsize=1),
        "lifecycle": TaskLifecycleRegistry(),
        "telemetry_delivery": {
            "state": "NORMAL",
            "dropped_messages_total": 0,
            "dropped_event_count": 0,
            "dropped_by_kind": {},
        },
    }
    monkeypatch.setitem(api.app.state.rooms, client_id, room)
    first = room["lifecycle"].record_event(_started("overflow_task")).envelope
    second = room["lifecycle"].record_event(_step(1, "overflow_task")).envelope

    api._enqueue(client_id, ("event", first))
    api._enqueue(client_id, ("event", second))

    assert room["queue"].qsize() == 1
    assert room["queue"].get_nowait() == ("event", second)
    assert api._delivery_status(room) == {
        "state": "DEGRADED_QUEUE_OVERFLOW",
        "dropped_messages_total": 1,
        "dropped_event_count": 1,
        "dropped_by_kind": {"event": 1},
        # [BOSS-11] Çerçeve hataları da raporlanır; kuyruk taşmasında sıfırdır.
        "frame_errors_total": 0,
        "frame_errors_by_kind": {},
    }


def test_queue_overflow_metrics_are_exposed_by_telemetry_api(monkeypatch):
    client_id = "overflow_api_test"
    room = api.get_room(client_id)
    room["telemetry_delivery"] = {
        "state": "DEGRADED_QUEUE_OVERFLOW",
        "dropped_messages_total": 4,
        "dropped_event_count": 2,
        "dropped_by_kind": {"event": 2, "log": 2},
    }

    async def no_browser():
        return {"instagram": False, "browser": False}

    monkeypatch.setattr(api, "_scraper_capability", no_browser)
    response = asyncio.run(api.api_telemetry(client_id))

    assert response["telemetry_delivery"]["state"] == "DEGRADED_QUEUE_OVERFLOW"
    assert response["telemetry_delivery"]["dropped_event_count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# [E-GÖZ3-2 · DAVRANIŞAL] Üretimde Redis düşüşü YASAK / geliştirmede GÖRÜNÜR
# (statik kilidin tamamlayıcısı: kapı FIILEN koşturulur — bak. §4.2 raporu)
# ─────────────────────────────────────────────────────────────────────────────

def test_production_redis_import_failure_is_hard_refusal(monkeypatch):
    """Üretim + Redis bus import'u düşerse: kapıda RuntimeError (fallback YOK)."""
    import sys as _sys

    from agent_core.workers import agent_worker as aw

    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setitem(_sys.modules, "agent_core.services.redis_bus", None)
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            aw.run_worker(
                "prod_refusal_agent",
                bus=None,
                heartbeat_interval=0.01,
                max_heartbeats=1,
                backend_url="",
            )
        )
    assert "PRODUCTION_REQUIRES_REDIS" in str(exc.value)


def test_dev_redis_import_failure_degrades_visibly(monkeypatch, caplog):
    """Geliştirme + Redis düşerse: süreç YAŞAR ama DEGRADED_MODE izi ERROR'dur."""
    import logging
    import sys as _sys

    from agent_core.workers import agent_worker as aw

    monkeypatch.delenv("PINEAL_ENV", raising=False)
    monkeypatch.setitem(_sys.modules, "agent_core.services.redis_bus", None)
    with caplog.at_level(logging.ERROR):
        asyncio.run(
            aw.run_worker(
                "dev_degraded_agent",
                bus=None,
                heartbeat_interval=0.01,
                max_heartbeats=1,
                backend_url="",
            )
        )
    assert "DEGRADED_MODE" in caplog.text
