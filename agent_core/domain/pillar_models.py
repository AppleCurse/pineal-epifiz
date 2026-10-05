"""Pineal 7-Pillar Wave-1 deterministic domain contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceStatus(str, Enum):
    OBSERVED = "OBSERVED"
    WEAK = "WEAK"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class WaveSample(StrictModel):
    t: datetime
    energy: float = Field(ge=0)
    post_count: int = Field(ge=0, default=0)
    mean_text_len: float = 0
    engagement: float = 0
    platform: str = "primary"


class FlowWindow(StrictModel):
    start: datetime
    end: datetime
    peak_energy: float
    mean_energy: float
    sample_count: int
    label: str = "flow"


class PhaseShift(StrictModel):
    platform_a: str
    platform_b: str
    lag_hours: float
    correlation: float = Field(ge=-1, le=1)
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    note: str = ""


class FrequencyReport(StrictModel):
    status: EvidenceStatus = EvidenceStatus.INSUFFICIENT_DATA
    samples: list[WaveSample] = Field(default_factory=list)
    waveform: list[float] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    peak_indices: list[int] = Field(default_factory=list)
    trough_indices: list[int] = Field(default_factory=list)
    flow_windows: list[FlowWindow] = Field(default_factory=list)
    friction_collapses: list[FlowWindow] = Field(default_factory=list)
    phase_shifts: list[PhaseShift] = Field(default_factory=list)
    dominant_period_days: float | None = None
    energy_mean: float = 0
    energy_std: float = 0
    night_energy_share: float = 0
    machine_note: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- FAZ B · B6: gerçek spektral analiz (FFT) ---
    # `dominant_period_days` declared ama hiç doldurulmayan bir kabuktu; artık
    # `agent_core.engines.spectrum` ile ÖLÇÜLEREK yazılır. Koşullar sağlanmazsa
    # (yettersiz kova / sabit seri) None kalır — periyot UYDURULMAZ.
    periodic_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    dominant_harmonic: int | None = None
    spectral_method: str = ""
    spectral_reason: str | None = None
    #: Normalize güç spektrumu (DC/Nyquist hariç) — UI spektrum grafiği için.
    spectrum: list[float] = Field(default_factory=list)


class SeismicKind(str, Enum):
    SILENCE_GAP = "SILENCE_GAP"
    ACTIVITY_BURST = "ACTIVITY_BURST"
    TONE_SHIFT = "TONE_SHIFT"
    STYLE_INVERSION = "STYLE_INVERSION"
    ENGAGEMENT_SHOCK = "ENGAGEMENT_SHOCK"
    CADENCE_BREAK = "CADENCE_BREAK"


class SeismicEvent(StrictModel):
    event_id: str
    kind: SeismicKind
    intensity: float = Field(ge=1, le=10)
    timestamp: datetime
    window_start: datetime
    window_end: datetime
    observables: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    hypotheses: list[str] = Field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence_refs: list[str] = Field(default_factory=list)


class SeismosReport(StrictModel):
    status: EvidenceStatus = EvidenceStatus.INSUFFICIENT_DATA
    events: list[SeismicEvent] = Field(default_factory=list)
    max_intensity: float = 0
    event_count: int = 0
    baseline_inter_post_hours: float | None = None
    machine_note: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AbsenceHypothesis(str, Enum):
    SUPPRESSION = "SUPPRESSION"
    DISINTEREST = "DISINTEREST"
    ROLE_BOUNDARY = "ROLE_BOUNDARY"
    AUDIENCE_FILTER = "AUDIENCE_FILTER"
    INSUFFICIENT_BASELINE = "INSUFFICIENT_BASELINE"
    UNKNOWN = "UNKNOWN"


class VoidSignal(StrictModel):
    topic: str
    category: str
    expected_presence: float = Field(ge=0, le=1)
    actual_presence: float = Field(ge=0, le=1)
    absence_delta: float
    absence_score: float = Field(ge=0, le=1)
    status: EvidenceStatus = EvidenceStatus.WEAK
    hypotheses: list[AbsenceHypothesis] = Field(default_factory=list)
    observables: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class VoidReport(StrictModel):
    status: EvidenceStatus = EvidenceStatus.INSUFFICIENT_DATA
    signals: list[VoidSignal] = Field(default_factory=list)
    top_voids: list[str] = Field(default_factory=list)
    global_absence_index: float = Field(ge=0, le=1, default=0)
    covered_categories: list[str] = Field(default_factory=list)
    machine_note: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PillarBundle(StrictModel):
    frequency: FrequencyReport = Field(default_factory=FrequencyReport)
    seismos: SeismosReport = Field(default_factory=SeismosReport)
    void: VoidReport = Field(default_factory=VoidReport)
    version: Literal["pillar-wave1-v1"] = "pillar-wave1-v1"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def as_snapshot_fields(self) -> dict[str, Any]:
        return {
            "frequency_map": self.frequency.model_dump(mode="json"),
            "seismos_events": self.seismos.model_dump(mode="json"),
            "void_map": self.void.model_dump(mode="json"),
            "pillar_bundle": self.model_dump(mode="json"),
        }
