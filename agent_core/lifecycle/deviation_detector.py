"""Sapma dedektörü — baseline'a göre sapmayı KANIT kaydına çevirir.

Dört kural (hepsi testlidir):
    1. **Deterministik kimlik**: ``evidence_id`` rastgele üretilmez.
       ``sha256(source_engine|temporal_basis|kanonik_anahtar)[:20]`` — aynı
       gözlem + aynı sonuç her koşuda aynı kimliği verir. Rastgele kimlik,
       SHA-256 kanıt mührünü kırar ve "bu kanıt nereden geldi?" sorusunu
       cevapsız bırakır.
    2. **Yokluk ≠ gözlem**: ``ritual.*`` sinyalinde 0.0, "gözlemledim ki sıfır"
       değil "bu etiket bu karede YOK" demektir → ``epistemic_type="absence"``.
    3. **Confound yapısal**: "aynı pencerede üretim biçimi de değişti" bilgisi
       metin sonuna iliştirilen bir not DEĞİL, ``source_metrics`` içinde
       makine-okunur alandır (``confounded_by_medium_change``).
    4. **İsim tutarlılığı**: sinyal adları ``default_specs`` ile birebir aynıdır;
       ``media.is_authored`` gibi bir kısaltma resolve edilemez, sessizce
       baseline dışında kalırdı.

Sınır: bu modül teşhis koymaz. Yalnız "hangi sinyal, ne zaman, kişinin kendi
merkezinden ne kadar saptı" sorusunu kanıt kaydına yazar.

Tüketici: ``agent_core.lifecycle.pipeline``, ``cluster_analyzer``.
Test: ``tests/lifecycle/test_lifecycle_deviation_detector.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional, Sequence

from agent_core.domain.evidence_models import EvidenceItem, EvidenceTimeline
from agent_core.lifecycle.baseline_builder import (
    DEFAULT_DEVIATION_Z,
    BaselineProfile,
    DeviationResult,
    SignalObservation,
    ensure_utc,
)
from agent_core.lifecycle.families import signal_family
from agent_core.lifecycle.medium_change import (
    DEFAULT_MEDIUM_THRESHOLD,
    MEDIUM_CHANGE_SIGNAL,
    MediumChangeAssessment,
    assess_medium_change,
    rate_in_window,
)
from agent_core.services.evidence_timeline import build_evidence_timeline as _canonical_timeline

#: Geriye dönük uyum için eski ad; tek kaynak ``medium_change`` modülüdür.
MEDIUM_SIGNAL = MEDIUM_CHANGE_SIGNAL
MEDIUM_SHIFT_THRESHOLD = DEFAULT_MEDIUM_THRESHOLD

EpistemicKind = Literal["observation", "absence", "inference"]

__all__ = [
    "DeviationFinding",
    "MEDIUM_SIGNAL",
    "MEDIUM_SHIFT_THRESHOLD",
    "build_evidence_timeline",
    "detect_deviations",
    "medium_shift_rate",
    "make_evidence_id",
    "to_evidence_item",
]

SOURCE_ENGINE = "life_rupture"


def make_evidence_id(source_engine: str, temporal_basis: str, canonical_key: str) -> str:
    """``^ev_[0-9a-f]{20}$`` sözleşmesine uyan deterministik kimlik."""
    payload = f"{source_engine}|{temporal_basis}|{canonical_key}".encode("utf-8")
    return "ev_" + hashlib.sha256(payload).hexdigest()[:20]


def _canonical_key(observation: SignalObservation, result: DeviationResult) -> str:
    return (
        f"{observation.signal_id}|{observation.source_ref}|{observation.timestamp.isoformat()}|"
        f"{observation.value:.10g}|{result.method}"
    )


def _epistemic_kind(finding: "DeviationFinding") -> EpistemicKind:
    return "absence" if finding.is_absence else "observation"


@dataclass(frozen=True)
class DeviationFinding:
    """Bir sapma: gözlem + baseline sonucu + eksen bilgisi."""

    observation: SignalObservation
    result: DeviationResult
    family: str
    confounded_by_medium_change: bool = False
    medium_change_status: str = "unknown"

    @property
    def signal_id(self) -> str:
        return self.observation.signal_id

    @property
    def timestamp(self) -> datetime:
        return self.observation.timestamp

    @property
    def is_absence(self) -> bool:
        """``True`` ise bu kayıt "gözledim ki sıfır" değil "bu karede YOK"dur."""
        return self.family == "ritual" and self.observation.value == 0.0


def medium_shift_rate(
    observations: Sequence[SignalObservation],
    window_start: datetime,
    window_end: datetime,
) -> Optional[float]:
    """Pencerede kurgulanmış/stüdyo üretim oranı (ölçülmediyse None).

    TEK BAŞINA confound kanıtı DEĞİLDİR: kişinin kendi baseline oranıyla
    karşılaştırma ``medium_change.assess_medium_change`` içinde yapılır.
    """
    return rate_in_window(observations, window_start, window_end)[0]


def detect_deviations(
    baseline: BaselineProfile,
    observations: Sequence[SignalObservation],
    window_start: datetime,
    window_end: datetime,
    *,
    z_threshold: float = DEFAULT_DEVIATION_Z,
    medium_change: Optional[MediumChangeAssessment] = None,
) -> list[DeviationFinding]:
    """Hedef penceredeki sapmaları bulur (kronolojik).

    Confound KARŞILAŞTIRMALIDIR: üretim biçimi kişinin kendi baseline dönemine
    göre değiştiyse (ve iki tarafta da ölçülebildiyse) habitat/somatik/ritüel
    sapmaları "yaşam koşulu değişimi" olarak okunamaz. Tek başına yüksek kurgu
    oranı confound değildir; ``unknown`` ise "confound yok" demek değildir.
    """
    start, end = ensure_utc(window_start), ensure_utc(window_end)
    target = [obs for obs in observations if start <= obs.timestamp <= end]

    assessment = medium_change or assess_medium_change(
        observations,
        baseline.baseline_window[0],
        baseline.baseline_window[1],
        start,
        end,
    )
    medium_shifted = assessment.is_shifted

    findings: list[DeviationFinding] = []
    for observation in target:
        result = baseline.evaluate(observation, z_threshold=z_threshold)
        if not result.is_deviation:
            continue
        family = signal_family(observation.signal_id)
        confounded = medium_shifted and family in ("habitat", "gaze", "ritual")
        findings.append(
            DeviationFinding(
                observation=observation,
                result=result,
                family=family,
                confounded_by_medium_change=confounded,
                medium_change_status=assessment.status,
            )
        )

    findings.sort(key=lambda finding: (finding.timestamp, finding.signal_id, finding.observation.source_ref))
    return findings


def to_evidence_item(finding: DeviationFinding, source_engine: str = SOURCE_ENGINE) -> EvidenceItem:
    """Bir sapmayı kanonik ``EvidenceItem`` sözleşmesine çevirir.

    Zaman çizelgesi sıralaması ve epistemik not metni burada YENİDEN
    yazılmaz: ``agent_core.services.evidence_timeline`` tek uygulamadır
    (pillar kanıtlarıyla aynı kapıdan geçer).
    """
    observation = finding.observation
    result = finding.result
    kind = _epistemic_kind(finding)
    evidence_id = make_evidence_id(source_engine, "observed_at", _canonical_key(observation, result))

    metrics: dict[str, Any] = {
        "signal_id": observation.signal_id,
        "family": finding.family,
        "source_ref": observation.source_ref,
        "value": observation.value,
        "baseline_center": result.baseline_center,
        "baseline_spread": result.baseline_spread,
        "distance": result.distance,
        "method": result.method,
        "confounded_by_medium_change": finding.confounded_by_medium_change,
        "medium_change_status": finding.medium_change_status,
    }
    if result.z_score is not None:
        metrics["z_score"] = result.z_score

    content = (
        f"{observation.signal_id}: kişisel merkez {result.baseline_center:.4g} → "
        f"gözlenen {observation.value:.4g} (fark {result.distance:.4g}, yöntem {result.method})"
    )
    if finding.confounded_by_medium_change:
        content += "; aynı pencerede üretim biçimi de değişti (confound kaydı)"

    return EvidenceItem(
        evidence_id=evidence_id,
        epistemic_type=kind,
        source_engine=source_engine,
        content=content,
        provenance_refs=[observation.source_ref],
        scope={
            "signal_id": observation.signal_id,
            "family": finding.family,
            "deviation_method": result.method,
            "life_rupture_schema": "life-rupture-v1",
        },
        observed_at=observation.timestamp,
        source_metrics=metrics,
    )


def build_evidence_timeline(
    findings: Sequence[DeviationFinding], source_engine: str = SOURCE_ENGINE
) -> EvidenceTimeline:
    """Sapmaları kronolojik, tiplenmiş ve mühürlenebilir zaman çizelgesine çevirir."""
    return _canonical_timeline(
        to_evidence_item(finding, source_engine=source_engine) for finding in findings
    )
