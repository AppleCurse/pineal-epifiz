"""Telemetri olay şeması — arayüze akan olayların TİPLİ sözleşmesi.

Olaylar: görev başladı/bitti/iptal edildi, adım tamamlandı, hata-durma,
insan onayı bekleniyor, frekans güncellemesi ve genel log. Her olay ``Severity``
ve ``AgentEventType`` taşır; ``TelemetryEvent`` WS çerçevesinin zarfıdır.

Bu şema istemci sözleşmesidir: alan adları/kodlar (ör. ``HALTED_*``,
``AWAITING_HUMAN``) frontend ve testlerle kilitlidir; arayüzde görünen her
durum gerçek bir olaydan gelmek zorundadır (uydurma durum yasağı).

Tüketici: ``backend/routes/websocket.py``, ``frontend/src/lib/telemetry.ts``.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Union
from pydantic import BaseModel, Field

class Severity(str, Enum):
    Info = "Info"
    Warning = "Warning"
    High = "High"
    Critical = "Critical"

class AgentEventType(str, Enum):
    TaskStarted = "TaskStarted"
    StepCompleted = "StepCompleted"
    ErrorHalt = "ErrorHalt"
    AwaitingHuman = "AwaitingHuman"
    TaskCompleted = "TaskCompleted"
    TaskCancelled = "TaskCancelled"
    FrequencyUpdate = "FrequencyUpdate"
    GenericLog = "GenericLog"

# Using discriminated unions for precise schema mirroring Rust's AgentEvent enum
class BaseAgentEvent(BaseModel):
    event_type: AgentEventType

class TaskStartedEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.TaskStarted
    task_id: str
    agent_name: str
    input_summary: str

class StepCompletedEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.StepCompleted
    task_id: str
    agent_name: str
    step_name: str
    output_hash: str

class ErrorHaltEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.ErrorHalt
    task_id: str
    agent_name: str
    error_code: str
    error_message: str
    severity: Severity

class AwaitingHumanEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.AwaitingHuman
    task_id: str
    agent_name: str
    reason: str
    options: List[str]

class TaskCompletedEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.TaskCompleted
    task_id: str
    agent_name: str
    final_result_hash: str
    duration_ms: int


class TaskCancelledEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.TaskCancelled
    task_id: str
    agent_name: str
    reason: str


class FrequencyUpdateEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.FrequencyUpdate
    task_id: str
    alignment_score: float
    authentic_anchor_count: int
    overall_frequency: str

class GenericLogEvent(BaseAgentEvent):
    event_type: AgentEventType = AgentEventType.GenericLog
    task_id: str
    message: str
    level: str = "INFO"

AgentEvent = Union[
    TaskStartedEvent,
    StepCompletedEvent,
    ErrorHaltEvent,
    AwaitingHumanEvent,
    TaskCompletedEvent,
    TaskCancelledEvent,
    FrequencyUpdateEvent,
    GenericLogEvent
]

class TelemetryEvent(BaseModel):
    task_id: str
    run_id: str
    sequence: int = Field(ge=1)
    event_type: AgentEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: AgentEvent
    correlation_id: Optional[str] = None
    delivery_state: str = "NORMAL"
    dropped_event_count: int = Field(default=0, ge=0)
