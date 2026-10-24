"""Yaşam kırılması raporu — mühürlenebilir, tiplenmiş çıktı sözleşmesi.

İlkeler:
    * **Teşhis yok**: ``root_cause`` alanı yalnız ``UNKNOWN`` olabilir. Rapor
      "neden" sorusuna cevap vermez; "ne, ne zaman, hangi eksende, kalıcı mı"
      sorusuna cevap verir.
    * **Yorum kelimesi yok**: özet satırları sayı ve eksen adı taşır
      (depresyon/mutluluk/yalnızlık gibi etiketler YASAK — testle kilitli).
    * **Ölçülemeyen eksen saklanmaz**: ``axes`` listesi her eksen için
      ``measured`` / ``suppressed`` / ``unavailable`` durumunu ve GEREKÇESİNİ
      taşır. "Veri yok" ile "ölçüm yapılmadı" ekranda ayrılır.

Tüketici: ``agent_core.lifecycle.pipeline``, ``agent_core.task_executor``
(``status.life_rupture``), kanıt zinciri mühürü.
Test: ``tests/lifecycle/test_lifecycle_pipeline.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from agent_core.domain.evidence_models import EvidenceTimeline

RuptureStatus = Literal[
    "RUPTURE_CONFIRMED",
    "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE",
    "NO_RUPTURE",
    "INSUFFICIENT_BASELINE",
    "INSUFFICIENT_DATA",
]

AxisState = Literal["measured", "suppressed", "unavailable"]

__all__ = ["AxisReport", "LifeRuptureReport", "RuptureStatus"]


class AxisReport(BaseModel):
    """Tek bir ölçüm ekseninin durumu ve gerekçesi."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    axis: str
    state: AxisState
    reason: str = ""
    baseline_signal_count: int = 0
    deviating_signals: list[str] = Field(default_factory=list)


class LifeRuptureReport(BaseModel):
    """Boylamsal sapma raporu (``life-rupture-v1``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["life-rupture-v1"] = "life-rupture-v1"
    subject_id: str
    status: RuptureStatus

    baseline_window_start: Optional[datetime] = None
    baseline_window_end: Optional[datetime] = None
    target_window_start: Optional[datetime] = None
    target_window_end: Optional[datetime] = None
    cluster_window_start: Optional[datetime] = None
    cluster_window_end: Optional[datetime] = None

    family_count: int = 0
    families: dict[str, list[str]] = Field(default_factory=dict)
    persistence_days: float = 0.0
    deviation_count: int = 0

    medium_shift_rate: Optional[float] = None
    confounded_axes: list[str] = Field(default_factory=list)

    #: Teşhis YASAK: rapor yalnız "bilinmiyor" diyebilir.
    root_cause: Literal["UNKNOWN"] = "UNKNOWN"
    falsification_checks: list[str] = Field(default_factory=list)

    axes: list[AxisReport] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)

    #: Pillar Strata'nın ön-hesaplanmış erken/geç kayıtları (bağımsız sayılmaz).
    prior_pillar_evidence: list[dict[str, Any]] = Field(default_factory=list)
    prior_pillar_counts_toward_cluster: Literal[False] = False

    evidence_timeline: Optional[EvidenceTimeline] = None
    evidence_entry_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    machine_note: str = ""
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
