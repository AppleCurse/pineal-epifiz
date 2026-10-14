"""Deterministic task event sequencing and terminal-state protection."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from agent_core.schemas.telemetry import AgentEvent, AgentEventType, TelemetryEvent


class LifecycleState(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    HALTED = "HALTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset({
    LifecycleState.COMPLETED,
    LifecycleState.HALTED,
    LifecycleState.FAILED,
    LifecycleState.CANCELLED,
})


@dataclass
class LifecycleRun:
    task_id: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: LifecycleState = LifecycleState.ACTIVE
    sequence: int = 0
    fingerprints: set[str] = field(default_factory=set)
    terminal_snapshot_fingerprint: Optional[str] = None
    terminal_event_recorded: bool = False
    # [AUDIT R1] Son etkinlik anı (monotonik). Sweep, sadece ETKİNLİĞİ eski
    # run'ları düşer — böylece "uzun süredir dokunulmamış terminal görev"
    # bellekten çıkar, taze run'lar dokunulmaz.
    last_activity: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class LifecycleDecision:
    accepted: bool
    outcome: str
    envelope: Optional[TelemetryEvent] = None
    state: LifecycleState = LifecycleState.ACTIVE


class TaskLifecycleRegistry:
    """Room-scoped lifecycle authority.

    Sequence assignment, duplicate checks, and terminal transitions happen
    under one lock. A terminal run can never become active again.
    """

    def __init__(self):
        self._runs: Dict[str, LifecycleRun] = {}
        self._lock = threading.Lock()
        self.duplicate_events = 0
        self.rejected_terminal_events = 0
        self.rejected_terminal_mutations = 0
        self.idempotent_terminal_requests = 0
        # [AUDIT R1] Oda başına registry task_id ile BÜYÜDÜĞÜ için (WS'li oda
        # evict'ten muaf -> ölümsüz) terminal run'lar bir RETENTION süresi
        # sonra geri kazanılır. Eşik/TTL'siz sınırsız büyüme (P0-2/P0-5
        # deseninin üçüncü tekrarı) kapatılır: boyut artık "retention süresi x
        # görev hızı" ile sınırlıdır, toplam görev sayısı ile değil.
        try:
            self.retention_seconds = max(60.0, float(os.getenv(
                "PINEAL_LIFECYCLE_RETENTION_SECONDS", "1800")))
        except (TypeError, ValueError):
            self.retention_seconds = 1800.0
        self._sweep_interval_seconds = 30.0
        self._last_sweep = 0.0
        self.swept = 0

    def _run(self, task_id: str) -> LifecycleRun:
        run = self._runs.get(task_id)
        if run is None:
            run = LifecycleRun(task_id=task_id)
            self._runs[task_id] = run
        return run

    @staticmethod
    def _fingerprint(payload: object) -> str:
        if hasattr(payload, "model_dump"):
            value = payload.model_dump(mode="json", warnings=False)
        else:
            value = payload
        encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _event_terminal_state(event_type: AgentEventType) -> Optional[LifecycleState]:
        if event_type == AgentEventType.TaskCompleted:
            return LifecycleState.COMPLETED
        if event_type == AgentEventType.ErrorHalt:
            return LifecycleState.HALTED
        if event_type == AgentEventType.TaskCancelled:
            return LifecycleState.CANCELLED
        return None

    @staticmethod
    def normalize_state(status: object) -> LifecycleState:
        value = getattr(status, "value", status)
        normalized = str(value or "").strip().lower()
        if normalized.startswith("halted"):
            return LifecycleState.HALTED
        if normalized in {"completed", "partially_completed"}:
            return LifecycleState.COMPLETED
        if normalized in {"failed", "error"}:
            return LifecycleState.FAILED
        if normalized in {"cancelled", "canceled"}:
            return LifecycleState.CANCELLED
        return LifecycleState.ACTIVE

    def record_event(self, event: AgentEvent) -> LifecycleDecision:
        task_id = getattr(event, "task_id", "")
        if not task_id:
            raise ValueError("Telemetry events require task_id")
        event_type = event.event_type
        fingerprint = self._fingerprint(event)

        with self._lock:
            run = self._run(task_id)
            if fingerprint in run.fingerprints:
                self.duplicate_events += 1
                return LifecycleDecision(False, "DUPLICATE", state=run.state)
            terminal_state = self._event_terminal_state(event_type)
            if run.state in TERMINAL_STATES:
                # The final snapshot can precede its terminal event in the
                # executor. Permit that one matching terminal confirmation.
                if terminal_state != run.state or run.terminal_event_recorded:
                    self.rejected_terminal_events += 1
                    return LifecycleDecision(False, "TERMINAL_STATE", state=run.state)

            run.sequence += 1
            run.last_activity = self._clock_now()
            run.fingerprints.add(fingerprint)
            if terminal_state is not None:
                run.state = terminal_state
                run.terminal_event_recorded = True
            envelope = TelemetryEvent(
                task_id=task_id,
                run_id=run.run_id,
                sequence=run.sequence,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                event=event,
            )
            return LifecycleDecision(True, "ACCEPTED", envelope=envelope, state=run.state)

    def transition(self, task_id: str, requested: object) -> LifecycleDecision:
        requested_state = self.normalize_state(requested)
        with self._lock:
            run = self._run(task_id)
            if run.state in TERMINAL_STATES:
                if requested_state == run.state:
                    self.idempotent_terminal_requests += 1
                    return LifecycleDecision(True, "IDEMPOTENT", state=run.state)
                self.rejected_terminal_mutations += 1
                return LifecycleDecision(False, "TERMINAL_STATE", state=run.state)
            run.state = requested_state
            run.last_activity = self._clock_now()
            return LifecycleDecision(True, "TRANSITIONED", state=run.state)

    def reopen(self, task_id: str, requested: object) -> LifecycleDecision:
        """[B0 · DESTEKLE DEVAM] Terminal koşu resume için YENİDEN AÇILIR.

        Durum makinesi DEĞİŞTİRİLMEDİ: terminal durumlar (halted_*/failed/…)
        mevcut; yalnızca ``resume`` kanıtı olan koşu ``terminal → processing``
        tek geçişiyle tekrar canlıya alınabilir. Terminal işaretçileri
        (event/snapshot fingerprint) sıfırlanır, sıra (sequence) ve parmak
        izleri korunur — böylece eski olaylar yeniden kabul edilmez, yeni
        olaylar reddedilmez.
        """
        requested_state = self.normalize_state(requested)
        with self._lock:
            run = self._run(task_id)
            if run.state not in TERMINAL_STATES:
                if run.state == requested_state:
                    return LifecycleDecision(True, "IDEMPOTENT", state=run.state)
                run.state = requested_state
                run.last_activity = self._clock_now()
                return LifecycleDecision(True, "TRANSITIONED", state=run.state)
            run.state = requested_state
            run.terminal_event_recorded = False
            run.terminal_snapshot_fingerprint = None
            run.last_activity = self._clock_now()
            return LifecycleDecision(True, "REOPENED", state=run.state)

    def accept_snapshot(self, snapshot: object) -> LifecycleDecision:
        task_id = getattr(snapshot, "task_id", "")
        if not task_id:
            raise ValueError("Task snapshots require task_id")
        requested_state = self.normalize_state(getattr(snapshot, "status", None))
        fingerprint = self._fingerprint(snapshot)

        with self._lock:
            run = self._run(task_id)
            if run.state in TERMINAL_STATES:
                if requested_state != run.state:
                    self.rejected_terminal_mutations += 1
                    return LifecycleDecision(False, "TERMINAL_STATE", state=run.state)
                if run.terminal_snapshot_fingerprint is None:
                    # A terminal event may reach the bus just before its final
                    # snapshot. Exactly one matching terminal snapshot is valid.
                    run.terminal_snapshot_fingerprint = fingerprint
                    return LifecycleDecision(True, "TERMINAL_SNAPSHOT", state=run.state)
                if fingerprint == run.terminal_snapshot_fingerprint:
                    return LifecycleDecision(True, "IDEMPOTENT", state=run.state)
                self.rejected_terminal_mutations += 1
                return LifecycleDecision(False, "TERMINAL_STATE", state=run.state)

            run.state = requested_state
            run.last_activity = self._clock_now()
            if requested_state in TERMINAL_STATES:
                run.terminal_snapshot_fingerprint = fingerprint
            return LifecycleDecision(True, "SNAPSHOT", state=run.state)

    def terminate(self, task_id: str, action: str) -> LifecycleDecision:
        normalized = action.strip().lower()
        if normalized == "halt":
            requested = LifecycleState.HALTED
        elif normalized in {"cancel", "cancelled", "canceled"}:
            requested = LifecycleState.CANCELLED
        else:
            raise ValueError(f"Unsupported terminal action: {action}")
        return self.transition(task_id, requested)

    @staticmethod
    def _clock_now() -> float:
        return time.monotonic()

    def sweep(self, now: Optional[float] = None, live_task_ids: Optional[set] = None) -> int:
        """[AUDIT R1] Eski run'ları geri kazanır (oda-özel bellek sızıntısı kapanışı).

        Kurallar:
        - YENİ (retention içinde) run'lara ASLA dokunulmaz.
        - TERMINAL run: retention dolunca düşer (cancel/halt geçmişe bakılmaz;
          `/api/tasks` listesi dosyaya bakar, registry'ye değil).
        - ACTIVE run: `live_task_ids` verilip run bu kümede değilse VE
          retention dolduysa düşer (askıya kalmış/ölü görev). `live_task_ids`
          None ise ACTIVE run'lara hiç dokunulmaz (muhafazakar varsayılan).

        Amortize maliyet: registry başına en fazla ~30 sn'de bir O(N) tarama
        (deadline throttle); geri kalan çağrılar tek float karşılaştırması.
        Dönen değer düşürülen run sayısıdır.
        """
        if now is None:
            now = time.monotonic()
        if now - self._last_sweep < self._sweep_interval_seconds:
            return 0
        self._last_sweep = now
        removed = 0
        with self._lock:
            for task_id in list(self._runs):
                run = self._runs.get(task_id)
                if run is None:
                    continue
                if now - run.last_activity <= self.retention_seconds:
                    continue
                if run.state in TERMINAL_STATES:
                    del self._runs[task_id]
                    removed += 1
                elif live_task_ids is not None and task_id not in live_task_ids:
                    del self._runs[task_id]
                    removed += 1
            if removed:
                self.swept += removed
        return removed

    def get_run(self, task_id: str) -> Optional[dict]:
        with self._lock:
            run = self._runs.get(task_id)
            if run is None:
                return None
            return {
                "task_id": run.task_id,
                "run_id": run.run_id,
                "state": run.state.value,
                "last_sequence": run.sequence,
            }

    def metrics(self) -> dict:
        with self._lock:
            return {
                "runs": len(self._runs),
                "duplicate_events": self.duplicate_events,
                "rejected_terminal_events": self.rejected_terminal_events,
                "rejected_terminal_mutations": self.rejected_terminal_mutations,
                "idempotent_terminal_requests": self.idempotent_terminal_requests,
                "swept": self.swept,
            }
