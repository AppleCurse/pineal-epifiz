"""Yaşam kırılması raporu — mühürlenebilir, tiplenmiş çıktı sözleşmesi.

İlkeler:
    * **Teşhis yok**: ``root_cause`` alanı yalnız ``UNKNOWN`` olabilir. Rapor
      "neden" sorusuna cevap vermez; "ne, ne zaman, hangi eksende, kalıcı mı,
      neyi ölçemedim" sorusuna cevap verir.
    * **Yorum kelimesi yok**: özet satırları sayı ve eksen adı taşır
      (depresyon/mutluluk/yalnızlık gibi etiketler YASAK — testle kilitli).
    * **Her bulgu denetlenebilir**: tek satır yerine ``Finding`` kaydı; hangi
      dönem, hangi baseline değeri, hangi gözlem, hangi yöntem, hangi eşik,
      hangi kalıcılık, hangi bağımsızlık durumu, hangi kaynaklar.
    * **Ölçülemeyen saklanmaz**: ``unknowns`` ve ``excluded_evidence``
      bölümleri "ne bilmiyorum" sorusunu yazılı cevaplar. Sessiz boşluk yok.
    * **Kimlik deterministik**: ``report_id`` yalnız kanıt + yapılandırmadan
      türetilir; ``computed_at`` kimliği değiştirmez.

Tüketici: ``agent_core.lifecycle.pipeline``, ``agent_core.task_executor``
(``status.life_rupture``), kanıt zinciri mühürü.
Test: ``tests/lifecycle/test_lifecycle_pipeline.py``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_core.domain.evidence_models import EvidenceTimeline

RuptureStatus = Literal[
    "RUPTURE_CONFIRMED",
    "RUPTURE_CANDIDATE",
    "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE",
    "NO_RUPTURE",
    "INSUFFICIENT_BASELINE",
    "INSUFFICIENT_DATA",
]

#: Sözleşme §10: beş küme durumu birbirine karıştırılmaz.
ClusterState = Literal[
    "DETECTED",
    "CANDIDATE",
    "INSUFFICIENT_EVIDENCE",
    "NO_SIGNIFICANT_CLUSTER",
    "CONFOUNDED",
]

AxisState = Literal["measured", "suppressed", "unavailable"]

Direction = Literal["increased", "decreased", "appeared", "disappeared", "changed", "stable", "unknown"]
MeasurementStatus = Literal["measured", "partial", "not_measurable", "insufficient_data", "confounded"]
IndependenceStatus = Literal["confirmed", "unknown", "dependent", "not_applicable"]

__all__ = [
    "AxisReport",
    "Finding",
    "LifeRuptureReport",
    "RuptureStatus",
    "compute_report_id",
]


class AxisReport(BaseModel):
    """Tek bir ölçüm ekseninin durumu ve gerekçesi."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    axis: str
    state: AxisState
    reason: str = ""
    baseline_signal_count: int = 0
    deviating_signals: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """Tek bir sinyalin denetlenebilir bulgu kaydı (sözleşme §11.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str
    signal_id: str
    signal_family: str
    baseline_period: dict[str, Any]
    comparison_period: dict[str, Any]
    baseline_value: Optional[float]
    observed_value: Optional[float]
    delta: Optional[float]
    direction: Direction
    deviation_method: str
    threshold_or_tolerance: Optional[float]
    persistence: dict[str, Any]
    independence_status: IndependenceStatus
    measurement_status: MeasurementStatus
    deviation_count: int = 0
    source_refs: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    alternative_explanations: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class LifeRuptureReport(BaseModel):
    """Boylamsal sapma raporu (``life-rupture-v1``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["life-rupture-v1"] = "life-rupture-v1"
    report_id: str = ""
    subject_id: str
    status: RuptureStatus
    cluster_state: ClusterState = "NO_SIGNIFICANT_CLUSTER"

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

    candidate_signal_count: int = 0
    confirmed_independent_signal_count: int = 0
    independence_assessment: dict[str, Any] = Field(default_factory=dict)
    medium_change_assessment: dict[str, Any] = Field(default_factory=dict)
    medium_shift_rate: Optional[float] = None
    confounded_axes: list[str] = Field(default_factory=list)

    #: Teşhis YASAK: rapor yalnız "bilinmiyor" diyebilir.
    root_cause: Literal["UNKNOWN"] = "UNKNOWN"
    falsification_checks: list[str] = Field(default_factory=list)
    decision_summary: str = ""

    axes: list[AxisReport] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    data_coverage: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    recoveries: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    excluded_evidence: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    summary: list[str] = Field(default_factory=list)

    #: Pillar Strata'nın ön-hesaplanmış erken/geç kayıtları (bağımsız sayılmaz).
    prior_pillar_evidence: list[dict[str, Any]] = Field(default_factory=list)
    prior_pillar_counts_toward_cluster: Literal[False] = False

    #: İkinci kademe model etiketleri — ÖLÇÜM DEĞİL, ÇIKARIM.
    #: ``ritual.*`` sözlüğü buradan beslenmez; bu yüzden küme kanıtı sayılmaz.
    semantic_inferences: list[dict[str, Any]] = Field(default_factory=list)
    semantic_inference_count: int = 0
    semantic_inferences_count_toward_cluster: Literal[False] = False

    #: Kanıt dereceleri: ``measured`` (araç ölçümü) ve ``corroborated`` (iki
    #: bağımsız modelin mutabakatı). İkisi AYNI kefeye konmaz.
    evidence_grade_counts: dict[str, int] = Field(default_factory=dict)
    corroborated_signal_count: int = 0
    corroborated_labels: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("corroborated_labels")
    @classmethod
    def _corroborated_rows_are_corroborated(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Mutabakat satırı ``measured`` diye rapora GİREMEZ."""
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("corroborated_labels satırı sözlük olmalı")
            if row.get("observation_grade") != "corroborated":
                raise ValueError("corroborated_labels yalnız observation_grade='corroborated' taşır")
            if int(row.get("agreement_count") or 0) < 2:
                raise ValueError("corroborated_labels en az 2 bağımsız görünüm ister")
        return rows

    @field_validator("semantic_inferences")
    @classmethod
    def _inferences_stay_inferences(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Model iddiası rapora ``observation`` olarak GİREMEZ (sözleşme kilidi)."""
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("semantic_inferences satırı sözlük olmalı")
            if row.get("epistemic_type") != "inference":
                raise ValueError("semantic_inferences yalnız epistemic_type='inference' taşır")
            if row.get("counts_toward_cluster") is not False:
                raise ValueError("semantic_inferences küme kanıtı sayılamaz")
        return rows

    evidence_timeline: Optional[EvidenceTimeline] = None
    evidence_entry_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    machine_note: str = ""
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def compute_report_id(payload: dict[str, Any]) -> str:
    """Kanıttan deterministik rapor kimliği (``lr_<20 hex>``).

    ``computed_at`` gibi çalışma zamanı alanları DIŞARIDA bırakılır; aksi
    hâlde aynı kanıt her koşuda farklı kimlik alır ve mühür anlamsızlaşır.
    """
    stable = {key: value for key, value in payload.items() if key != "computed_at"}
    canonical = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str)
    return "lr_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
