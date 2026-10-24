"""Üretim biçimi değişimi — karıştırıcı etkenin ÖLÇÜLMESİ (tahmini değil).

Eski (yanlış) kural: "değişim penceresinde kurgu oranı %50'yi geçtiyse confound
vardır." Bu kural, HER ZAMAN yoğun kurgu üreten bir hesabı da "değişti" diye
işaretler — oysa kişinin üretim biçimi hiç değişmemiştir. Aynı şekilde, hiç
kurgu kullanmayan bir hesapta da hiçbir şey yakalamaz.

Doğru soru şudur: **kişinin KENDİ başlangıç dönemine göre üretim biçimi
değişti mi?**

    baseline_rate     = authored oranı (baseline penceresi)
    comparison_rate   = authored oranı (karşılaştırma penceresi)
    delta             = comparison_rate − baseline_rate
    status            = changed | stable | unknown

Üç sonuç, üç ayrı şey söyler:

    * ``changed``  : |delta| > threshold → o pencerede üretim biçimi kaydı.
                     Yalnız bu durumda habitat/somatik/ritüel eksenleri
                     "karşılaştırılamaz" işaretlenir.
    * ``stable``   : yeterli örneklem var ve kayma yok → yüksek ama SABİT
                     kurgu oranı confound DEĞİLDİR.
    * ``unknown``  : iki taraftan birinde yeterli örneklem yok → "confound yok"
                     sonucu ÇIKARILAMAZ (ölçülemeyen, sıfır değildir).

Tüketici: ``agent_core.lifecycle.deviation_detector``, ``cluster_analyzer``.
Test: ``tests/lifecycle/test_lifecycle_medium_change.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Sequence

from agent_core.lifecycle.baseline_builder import SignalObservation, ensure_utc

__all__ = [
    "DEFAULT_MEDIUM_THRESHOLD",
    "MIN_MEDIUM_SAMPLES",
    "MEDIUM_CHANGE_SIGNAL",
    "MediumChangeAssessment",
    "assess_medium_change",
    "rate_in_window",
]

MEDIUM_CHANGE_SIGNAL = "media.is_authored_or_staged"
#: Oran farkı bu eşiğin üstündeyse "üretim biçimi değişti" denir (yapılandırılır).
DEFAULT_MEDIUM_THRESHOLD = 0.25
#: Her iki pencerede asgari örneklem; altında sonuç ``unknown``dur.
MIN_MEDIUM_SAMPLES = 5

MediumChangeStatus = Literal["changed", "stable", "unknown"]


@dataclass(frozen=True)
class MediumChangeAssessment:
    """Üretim biçimi kaymasının yapılandırılmış kaydı."""

    status: MediumChangeStatus
    baseline_rate: Optional[float]
    comparison_rate: Optional[float]
    delta: Optional[float]
    threshold: float
    baseline_sample_size: int
    comparison_sample_size: int
    reasons: tuple[str, ...] = ()

    @property
    def is_shifted(self) -> bool:
        return self.status == "changed"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "baseline_rate": self.baseline_rate,
            "comparison_rate": self.comparison_rate,
            "delta": self.delta,
            "threshold": self.threshold,
            "baseline_sample_size": self.baseline_sample_size,
            "comparison_sample_size": self.comparison_sample_size,
            "reasons": list(self.reasons),
        }


def rate_in_window(
    observations: Sequence[SignalObservation],
    window_start: datetime,
    window_end: datetime,
) -> tuple[Optional[float], int]:
    """Pencerede authored oranı ve örneklem sayısı (ölçüm yoksa ``(None, 0)``)."""
    start, end = ensure_utc(window_start), ensure_utc(window_end)
    values = [
        obs.value
        for obs in observations
        if obs.signal_id == MEDIUM_CHANGE_SIGNAL and start <= obs.timestamp <= end
    ]
    if not values:
        return None, 0
    return sum(values) / len(values), len(values)


def assess_medium_change(
    observations: Sequence[SignalObservation],
    baseline_start: datetime,
    baseline_end: datetime,
    comparison_start: datetime,
    comparison_end: datetime,
    *,
    threshold: float = DEFAULT_MEDIUM_THRESHOLD,
    min_samples: int = MIN_MEDIUM_SAMPLES,
) -> MediumChangeAssessment:
    """İki pencere arasındaki üretim biçimi kaymasını ölçer.

    ``unknown`` bir "hayır" değildir: ölçülemeyen durum sıfır sayılamaz.
    """
    baseline_rate, baseline_n = rate_in_window(observations, baseline_start, baseline_end)
    comparison_rate, comparison_n = rate_in_window(observations, comparison_start, comparison_end)

    reasons: list[str] = []
    if baseline_rate is None or baseline_n < min_samples:
        reasons.append(
            f"baseline penceresinde yeterli üretim biçimi gözlemi yok "
            f"(n={baseline_n} < {min_samples}); karşılaştırma yapılamaz"
        )
    if comparison_rate is None or comparison_n < min_samples:
        reasons.append(
            f"karşılaştırma penceresinde yeterli üretim biçimi gözlemi yok "
            f"(n={comparison_n} < {min_samples}); karşılaştırma yapılamaz"
        )

    if reasons:
        return MediumChangeAssessment(
            status="unknown",
            baseline_rate=baseline_rate,
            comparison_rate=comparison_rate,
            delta=None,
            threshold=threshold,
            baseline_sample_size=baseline_n,
            comparison_sample_size=comparison_n,
            reasons=tuple(reasons),
        )

    delta = comparison_rate - baseline_rate
    shifted = abs(delta) > threshold
    reasons.append(
        f"authored oranı {baseline_rate:.2f} → {comparison_rate:.2f} "
        f"(fark {delta:+.2f}; eşik {threshold:.2f})"
    )
    if not shifted:
        reasons.append("oran yüksek olsa da DÖNEMSEL değişim yok; tek başına confound değildir")

    return MediumChangeAssessment(
        status="changed" if shifted else "stable",
        baseline_rate=baseline_rate,
        comparison_rate=comparison_rate,
        delta=delta,
        threshold=threshold,
        baseline_sample_size=baseline_n,
        comparison_sample_size=comparison_n,
        reasons=tuple(reasons),
    )
