"""Kalıcılık ölçümü — "iki uç nokta" yanılsamasının kapatıldığı yer.

Yanlış (ve yaygın) kural: ilk sapma 1 Ocak'ta, son sapma 5 Mart'ta görüldüyse
"60 gün sürdü" demek. Bu, arada hiç gözlem olmasa bile çalışır; yani ölçüm
değil, takvim çıkarmasıdır. İki uç nokta arası boşluk, sürekliliğin KANITI
değildir — kanıtı yokluğudur.

Doğru ölçüm, sinyalin kendi zaman serisini sabit dilimlere böler ve şunları
ayrı ayrı sayar:

    * ``eligible_windows``   — içinde ölçülebilir gözlem olan dilim sayısı
    * ``deviating_windows``  — sapmanın görüldüğü dilim sayısı
    * ``consecutive_deviation_windows`` — kesintisiz sapma serisinin uzunluğu
    * ``coverage_rate``      — kapsanan dilim / aralıktaki toplam dilim
    * ``longest_unobserved_gap_days`` — iki gözlem arasındaki en uzun boşluk

``not_measurable`` dilimler "sapma yok" sayılmaz: kapsama eksiği olarak kalır.
Bu yüzden ``persistent`` hükmü üç koşulun BİRLİKTE sağlanmasını ister:
yeterli ardışık dilim, yeterli takvim yayılımı ve yeterli kapsama.

Eşikler kodun içine gömülmez: ``PersistenceConfig`` ile beyan edilir ve rapora
yazılır (bilimsel eşik değil, ürün yapılandırmasıdır).

Tüketici: ``agent_core.lifecycle.cluster_analyzer``, ``pipeline``.
Test: ``tests/lifecycle/test_lifecycle_persistence.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional, Sequence

from agent_core.lifecycle.baseline_builder import SignalObservation, ensure_utc

__all__ = [
    "DEFAULT_PERSISTENCE_CONFIG",
    "PersistenceConfig",
    "PersistenceRecord",
    "measure_persistence",
]

PersistenceStatus = Literal["persistent", "intermittent", "transient", "insufficient_coverage"]


@dataclass(frozen=True)
class PersistenceConfig:
    """Kalıcılık eşikleri — beyan edilir, gizlenmez.

    ``bucket_days``     : zaman serisi dilim genişliği (gün).
    ``min_consecutive_windows`` : "kalıcı" için kesintisiz sapma dilimi sayısı.
    ``min_span_days``   : sapmanın yayılması gereken asgari takvim süresi.
    ``min_coverage_rate`` : aralıktaki dilimlerin asgari ölçülmüş oranı.
    ``max_unobserved_gap_days`` : bu boşluktan uzun sessizlik sürekliliği keser.
    """

    bucket_days: int = 7
    min_consecutive_windows: int = 3
    min_span_days: int = 60
    min_coverage_rate: float = 0.5
    max_unobserved_gap_days: float = 45.0

    def to_dict(self) -> dict:
        return {
            "bucket_days": self.bucket_days,
            "min_consecutive_windows": self.min_consecutive_windows,
            "min_span_days": self.min_span_days,
            "min_coverage_rate": self.min_coverage_rate,
            "max_unobserved_gap_days": self.max_unobserved_gap_days,
        }


DEFAULT_PERSISTENCE_CONFIG = PersistenceConfig()


@dataclass(frozen=True)
class PersistenceRecord:
    """Bir sinyalin kalıcılık kaydı (rapora alan alan yazılır)."""

    status: PersistenceStatus
    first_observed_at: Optional[datetime]
    last_observed_at: Optional[datetime]
    observed_windows: int
    eligible_windows: int
    deviating_windows: int
    consecutive_deviation_windows: int
    coverage_rate: Optional[float]
    longest_unobserved_gap_days: Optional[float]
    persistence_days: Optional[float]
    measurable_observation_count: int
    config: dict = field(default_factory=dict)
    reasons: tuple[str, ...] = ()

    @property
    def is_persistent(self) -> bool:
        return self.status == "persistent"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "first_observed_at": self.first_observed_at.isoformat() if self.first_observed_at else None,
            "last_observed_at": self.last_observed_at.isoformat() if self.last_observed_at else None,
            "observed_windows": self.observed_windows,
            "eligible_windows": self.eligible_windows,
            "deviating_windows": self.deviating_windows,
            "consecutive_deviation_windows": self.consecutive_deviation_windows,
            "coverage_rate": self.coverage_rate,
            "longest_unobserved_gap_days": self.longest_unobserved_gap_days,
            "persistence_days": self.persistence_days,
            "measurable_observation_count": self.measurable_observation_count,
            "config": dict(self.config),
            "reasons": list(self.reasons),
        }


def _bucket_index(moment: datetime, origin: datetime, bucket_days: int) -> int:
    return int((moment - origin).total_seconds() // (bucket_days * 86400))


def _longest_run(buckets: Sequence[int]) -> int:
    if not buckets:
        return 0
    ordered = sorted(set(buckets))
    best = run = 1
    for previous, current in zip(ordered, ordered[1:]):
        run = run + 1 if current == previous + 1 else 1
        best = max(best, run)
    return best


def measure_persistence(
    observations: Sequence[SignalObservation],
    deviation_timestamps: Sequence[datetime],
    *,
    config: PersistenceConfig = DEFAULT_PERSISTENCE_CONFIG,
) -> PersistenceRecord:
    """Bir sinyalin sapmasının gerçekten SÜREKLİ olup olmadığını ölçer.

    ``observations`` sinyalin TÜM ölçülebilir gözlemleri (baseline + hedef),
    ``deviation_timestamps`` yalnız sapma olarak işaretlenen anlar olmalıdır.
    Eksik gözlem "sapma yok" sayılmaz; kapsama oranını düşürür.
    """
    config_dict = config.to_dict()
    times = sorted(ensure_utc(obs.timestamp) for obs in observations)
    if not times:
        return PersistenceRecord(
            status="insufficient_coverage",
            first_observed_at=None,
            last_observed_at=None,
            observed_windows=0,
            eligible_windows=0,
            deviating_windows=0,
            consecutive_deviation_windows=0,
            coverage_rate=None,
            longest_unobserved_gap_days=None,
            persistence_days=None,
            measurable_observation_count=0,
            config=config_dict,
            reasons=("hiç ölçülebilir gözlem yok",),
        )

    deviations = sorted(ensure_utc(moment) for moment in deviation_timestamps if moment is not None)
    # Ölçüm aralığı SAPMANIN kendi yayılımıdır: iki yıl önceki sakin dönem,
    # bu yılki sapmanın sürekliliğini seyreltmemeli. Sapma yoksa tüm seri.
    span_start = deviations[0] if deviations else times[0]
    span_end = deviations[-1] if deviations else times[-1]
    in_span = [moment for moment in times if span_start <= moment <= span_end]
    if not in_span:
        in_span = [span_start, span_end]

    origin = span_start
    observed_buckets = {_bucket_index(moment, origin, config.bucket_days) for moment in in_span}
    deviation_buckets = {_bucket_index(moment, origin, config.bucket_days) for moment in deviations}

    span_seconds = max((span_end - span_start).total_seconds(), 0.0)
    total_buckets = int(span_seconds // (config.bucket_days * 86400)) + 1
    coverage_rate = len(observed_buckets) / total_buckets if total_buckets else None

    gaps = [(b - a).total_seconds() / 86400.0 for a, b in zip(in_span, in_span[1:])]
    longest_gap = max(gaps) if gaps else 0.0
    persistence_days = span_seconds / 86400.0

    consecutive = _longest_run(deviation_buckets)
    reasons: list[str] = []

    if not deviation_buckets:
        status: PersistenceStatus = "transient"
        reasons.append("bu sinyalde sapma kaydı yok")
    elif coverage_rate is not None and coverage_rate < config.min_coverage_rate:
        status = "insufficient_coverage"
        reasons.append(
            f"kapsama {coverage_rate:.2f} < {config.min_coverage_rate:.2f}; "
            "gözlenmeyen dilimler 'sapma yok' sayılmadı"
        )
    elif longest_gap > config.max_unobserved_gap_days:
        status = "insufficient_coverage"
        reasons.append(
            f"en uzun gözlem boşluğu {longest_gap:.0f} gün > "
            f"{config.max_unobserved_gap_days:.0f}; süreklilik kanıtlanamaz"
        )
    elif persistence_days < config.min_span_days:
        status = "transient"
        reasons.append(
            f"yayılım {persistence_days:.0f} gün < {config.min_span_days} gün; "
            "iki uç nokta kalıcılık değildir"
        )
    elif consecutive >= config.min_consecutive_windows:
        status = "persistent"
        reasons.append(
            f"{consecutive} ardışık sapma dilimi ≥ {config.min_consecutive_windows}; "
            f"kapsama {coverage_rate:.2f}"
        )
    else:
        status = "intermittent"
        reasons.append(
            f"kesintisiz dilim {consecutive} < {config.min_consecutive_windows}; "
            "sapma tekrar ediyor ama sürekli değil"
        )

    return PersistenceRecord(
        status=status,
        first_observed_at=span_start,
        last_observed_at=span_end,
        observed_windows=len(observed_buckets),
        eligible_windows=len(observed_buckets),
        deviating_windows=len(deviation_buckets),
        consecutive_deviation_windows=consecutive,
        coverage_rate=coverage_rate,
        longest_unobserved_gap_days=longest_gap,
        persistence_days=persistence_days,
        measurable_observation_count=len(times),
        config=config_dict,
        reasons=tuple(reasons),
    )


def span_days(first: Optional[datetime], last: Optional[datetime]) -> Optional[float]:
    """Yardımcı: iki zaman arasındaki gün (biri yoksa None)."""
    if first is None or last is None:
        return None
    return (ensure_utc(last) - ensure_utc(first)).total_seconds() / 86400.0


def window_bounds(origin: datetime, bucket: int, bucket_days: int) -> tuple[datetime, datetime]:
    """Dilim sınırları (rapor tarihleri için)."""
    start = ensure_utc(origin) + timedelta(days=bucket * bucket_days)
    return start, start + timedelta(days=bucket_days)
