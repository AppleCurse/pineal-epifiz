"""Küme analizi — tek sapma gürültü, iki sapma tesadüf, üç EKSEN desen.

Kurallar (hepsi testlidir):
    * **Kalıcılık**: ilk ve son sapma arasındaki takvim süresi KANIT DEĞİLDİR.
      Her sinyal için dilim bazlı ölçüm yapılır (``persistence``): kaç dilimde
      gözlem var, kaçında sapma var, kesintisiz seri kaç dilim, kapsama ne.
      İki uç nokta (1 Ocak + 5 Mart, arada hiçbir şey) kalıcılık sayılmaz.
    * **Rebound**: sapma sonra normale döndüyse kayıt düşürülür.
    * **Bağımsızlık DÜRÜST**: aynı aile tek eksendir; ayrıca farklı aileler
      arasındaki ilişki ölçülür. İlişki ÖLÇÜLEMİYORSA (korelasyon yok, sabit
      seri, yetersiz ortak gözlem) sinyaller bağımsız SAYILMAZ — durum
      ``unknown`` olur ve küme "doğrulandı" diye raporlanamaz. Ölçülemeyen
      bağımsızlık, bağımsızlık kanıtı değildir.
    * **Uç-nokta yasağı**: küme TÜM seri üzerinde kaydırmalı pencereyle aranır.

Bu modül "neden" sorusuna cevap vermez; yalnız "hangi pencerede kaç BAĞIMSIZ
eksen kalıcı olarak saptı" sorusunu sayar.

Tüketici: ``agent_core.lifecycle.pipeline``.
Test: ``tests/lifecycle/test_lifecycle_cluster_analyzer.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

from agent_core.lifecycle.baseline_builder import BaselineProfile, SignalObservation
from agent_core.lifecycle.deviation_detector import DeviationFinding
from agent_core.lifecycle.families import LIFE_AXES, signal_family
from agent_core.lifecycle.medium_change import MediumChangeAssessment
from agent_core.lifecycle.persistence import (
    DEFAULT_PERSISTENCE_CONFIG,
    PersistenceConfig,
    PersistenceRecord,
    measure_persistence,
)

__all__ = [
    "ClusterAnalysis",
    "IndependenceAssessment",
    "RuptureCluster",
    "SignalEpisode",
    "analyze_clusters",
    "DEFAULT_CLUSTER_WINDOW_DAYS",
    "DEFAULT_MIN_FAMILIES",
    "DEFAULT_MIN_PERSISTENCE_DAYS",
]

DEFAULT_CLUSTER_WINDOW_DAYS = 180
DEFAULT_MIN_FAMILIES = 3
#: Takvim yayılımı eşiği (persistence modülü ayrıca dilim/kapsama ölçer).
DEFAULT_MIN_PERSISTENCE_DAYS = 60
DEFAULT_CORRELATION_CUTOFF = 0.8


@dataclass(frozen=True)
class SignalEpisode:
    """Tek bir sinyalin sapma dönemi + kalıcılık kaydı."""

    signal_id: str
    family: str
    first_seen: datetime
    last_seen: datetime
    deviation_count: int
    persistence: PersistenceRecord

    @property
    def persistence_days(self) -> float:
        return (self.last_seen - self.first_seen).total_seconds() / 86400.0


@dataclass(frozen=True)
class IndependenceAssessment:
    """Bağımsızlık hükmü: doğrulandı / bilinmiyor / bağımlı.

    ``unknown`` bir "hayır" değildir: ölçülemeyen ilişki, bağımsızlık kanıtı
    sayılmaz ve küme "doğrulandı" diye raporlanamaz.
    """

    status: str  # confirmed | unknown | dependent | not_applicable
    method: str
    verified_pairs: tuple[tuple[str, str, float], ...] = ()
    unknown_pairs: tuple[tuple[str, str], ...] = ()
    merged_groups: tuple[tuple[str, ...], ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def is_confirmed(self) -> bool:
        return self.status == "confirmed"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "method": self.method,
            "verified_pairs": [
                {"left": a, "right": b, "correlation": r} for a, b, r in self.verified_pairs
            ],
            "unknown_pairs": [{"left": a, "right": b} for a, b in self.unknown_pairs],
            "merged_groups": [list(group) for group in self.merged_groups],
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RuptureCluster:
    """Aynı pencerede kümeleşen kalıcı sapmalar."""

    window_start: datetime
    window_end: datetime
    families: dict[str, tuple[str, ...]]
    persistence_records: dict[str, PersistenceRecord]
    independence: IndependenceAssessment
    medium_change: MediumChangeAssessment
    confounded_axes: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    candidate_signal_count: int = 0

    @property
    def family_count(self) -> int:
        return len(self.families)

    @property
    def signal_count(self) -> int:
        return sum(len(signals) for signals in self.families.values())

    @property
    def persistence_days(self) -> float:
        spans = [
            record.persistence_days
            for record in self.persistence_records.values()
            if record.persistence_days is not None
        ]
        return max(spans) if spans else 0.0

    @property
    def is_confounded(self) -> bool:
        """Üretim biçimi DEĞİŞTİ ve bu, okunamaz eksenleri etkiliyor mu?"""
        return bool(self.medium_change.is_shifted and self.confounded_axes)

    @property
    def is_verified(self) -> bool:
        """Küme ancak bağımsızlık DOĞRULANDIYSA kesinleşir."""
        return self.independence.is_confirmed and not self.is_confounded

    @property
    def confirmed_independent_signal_count(self) -> int:
        return self.family_count if self.independence.is_confirmed else 0


@dataclass
class ClusterAnalysis:
    """Küme taramasının sonucu (en iyi küme + neden bulunamadıysa gerekçeler)."""

    best: Optional[RuptureCluster] = None
    candidates: list[RuptureCluster] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    persistence_config: dict[str, Any] = field(default_factory=dict)


def _episodes(
    findings: Sequence[DeviationFinding],
    observations: Sequence[SignalObservation],
    config: PersistenceConfig,
) -> list[SignalEpisode]:
    by_signal: dict[str, list[DeviationFinding]] = {}
    for finding in findings:
        by_signal.setdefault(finding.signal_id, []).append(finding)

    episodes: list[SignalEpisode] = []
    for signal_id, items in by_signal.items():
        timestamps = sorted(finding.timestamp for finding in items)
        signal_observations = [obs for obs in observations if obs.signal_id == signal_id]
        record = measure_persistence(signal_observations, timestamps, config=config)
        episodes.append(
            SignalEpisode(
                signal_id=signal_id,
                family=items[0].family,
                first_seen=timestamps[0],
                last_seen=timestamps[-1],
                deviation_count=len(items),
                persistence=record,
            )
        )
    episodes.sort(key=lambda episode: (episode.first_seen, episode.signal_id))
    return episodes


def _rebounded(
    baseline: BaselineProfile,
    observations: Sequence[SignalObservation],
    episode: SignalEpisode,
    horizon: datetime,
) -> bool:
    """Sapma pencereden sonra normale döndü mü? (geri sıçrama denetimi)"""
    for observation in observations:
        if observation.signal_id != episode.signal_id:
            continue
        if not (episode.last_seen < observation.timestamp <= horizon):
            continue
        if not baseline.evaluate(observation).is_deviation:
            return True
    return False


def _family_pool(baseline: BaselineProfile) -> dict[str, tuple[str, ...]]:
    """Her ailenin baseline'da GÜVENİLİR tüm sinyalleri (ilişki ölçümü için).

    Bağımsızlık aile DÜZEYİNDE değerlendirilir: bir ailenin tek bir sabit
    sinyali yüzünden Pearson tanımsız kalırsa, aynı ailenin değişen sinyali
    temsilci olarak kullanılır. Ters kural (sabit sinyal → "bağımsız") tam da
    yasakladığımız varsayım olurdu.
    """
    pool: dict[str, list[str]] = {}
    for signal_id, signal_baseline in baseline.baselines.items():
        if not signal_baseline.is_reliable:
            continue
        pool.setdefault(signal_family(signal_id), []).append(signal_id)
    return {family: tuple(sorted(signals)) for family, signals in pool.items()}


def _assess_independence(
    families: dict[str, tuple[str, ...]],
    baseline: BaselineProfile,
    cutoff: float,
    pool: Optional[dict[str, tuple[str, ...]]] = None,
) -> tuple[dict[str, tuple[str, ...]], IndependenceAssessment]:
    """Aileleri korelasyona göre birleştirir ve bağımsızlık hükmünü yazar."""
    candidates = {name: (pool or {}).get(name, signals) for name, signals in families.items()}
    names = list(families)
    parent = {name: name for name in names}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    verified: list[tuple[str, str, float]] = []
    unknown: list[tuple[str, str]] = []
    merged: list[tuple[str, str, float]] = []

    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            correlation: Optional[float] = None
            for sig_left in candidates[left]:
                for sig_right in candidates[right]:
                    value = baseline.correlation_between(sig_left, sig_right)
                    if value is not None:
                        correlation = value
                        break
                if correlation is not None:
                    break
            if correlation is None:
                unknown.append((left, right))
                continue
            verified.append((left, right, correlation))
            if abs(correlation) >= cutoff:
                merged.append((left, right, correlation))
                parent[find(right)] = find(left)

    grouped: dict[str, list[str]] = {}
    for name in names:
        grouped.setdefault(find(name), []).extend(families[name])
    merged_families = {root: tuple(sorted(set(signals))) for root, signals in sorted(grouped.items())}

    merged_groups = tuple(
        tuple(sorted({name for name in names if find(name) == root}))
        for root in sorted(merged_families)
        if sum(1 for name in names if find(name) == root) > 1
    )

    if merged:
        status = "dependent"
        reasons = [
            f"|r| ≥ {cutoff:.2f}: {left} ≈ {right} (r={corr:.2f}) tek eksen sayıldı"
            for left, right, corr in merged
        ]
    elif unknown:
        status = "unknown"
        reasons = [
            f"{left} ↔ {right} ilişkisi ölçülemedi (ortak gözlem/korelasyon yok); "
            "bağımsızlık VARSAYILMADI"
            for left, right in unknown
        ]
    elif len(names) >= 2:
        status = "confirmed"
        reasons = [f"{len(verified)} aile çifti için ilişki ölçüldü ve eşiğin altında"]
    else:
        status = "not_applicable"
        reasons = ["tek eksen var; bağımsızlık iddiası kurulmadı"]

    assessment = IndependenceAssessment(
        status=status,
        method="pearson_baseline_joint",
        verified_pairs=tuple(verified),
        unknown_pairs=tuple(unknown),
        merged_groups=merged_groups,
        reasons=tuple(reasons),
    )
    return merged_families, assessment


def analyze_clusters(
    findings: Sequence[DeviationFinding],
    observations: Sequence[SignalObservation],
    baseline: BaselineProfile,
    *,
    window_days: int = DEFAULT_CLUSTER_WINDOW_DAYS,
    min_families: int = DEFAULT_MIN_FAMILIES,
    min_persistence_days: int = DEFAULT_MIN_PERSISTENCE_DAYS,
    correlation_cutoff: float = DEFAULT_CORRELATION_CUTOFF,
    medium_change: Optional[MediumChangeAssessment] = None,
    persistence_config: PersistenceConfig = DEFAULT_PERSISTENCE_CONFIG,
) -> ClusterAnalysis:
    """Kaydırmalı pencerelerle kalıcı, bağımsız, eşzamanlı sapma kümesi arar."""
    analysis = ClusterAnalysis(persistence_config=persistence_config.to_dict())
    episodes = _episodes(findings, observations, persistence_config)
    if not episodes:
        analysis.reasons.append("no_deviation: pencerede hiç sapma bulunmadı")
        return analysis

    horizon = max(observation.timestamp for observation in observations) if observations else episodes[-1].last_seen
    seen_windows: set[datetime] = set()

    for anchor in episodes:
        window_start = anchor.first_seen
        if window_start in seen_windows:
            continue
        seen_windows.add(window_start)
        window_end = window_start + timedelta(days=window_days)

        in_window = [episode for episode in episodes if window_start <= episode.first_seen <= window_end]
        kept: list[SignalEpisode] = []
        dropped: list[str] = []
        for episode in in_window:
            record = episode.persistence
            if record.status == "insufficient_coverage":
                dropped.append(f"{episode.signal_id}:insufficient_coverage")
                analysis.unknowns.append(
                    f"{episode.signal_id}: kalıcılık ölçülemedi "
                    f"(status=insufficient_coverage; {'; '.join(record.reasons)})"
                )
                continue
            if record.status != "persistent":
                dropped.append(f"{episode.signal_id}:persistence={record.status}")
                continue
            if record.persistence_days is None or record.persistence_days < min_persistence_days:
                dropped.append(f"{episode.signal_id}:span<{min_persistence_days}d")
                continue
            if _rebounded(baseline, observations, episode, window_end + timedelta(days=window_days)):
                dropped.append(f"{episode.signal_id}:rebound")
                continue
            kept.append(episode)

        if not kept:
            # Sessiz boşluk yok: "neden küme yok" sorusu cevapsız kalmaz.
            if dropped:
                analysis.reasons.append(
                    f"window {window_start.date()}: kalıcı/bağımsız aday yok; "
                    f"düşürülen kayıtlar: {', '.join(dropped)}"
                )
            continue

        grouped: dict[str, list[str]] = {}
        for episode in kept:
            grouped.setdefault(episode.family, []).append(episode.signal_id)
        family_signals = {family: tuple(sorted(signals)) for family, signals in grouped.items()}

        # Aynı ailedeki sinyaller tek ölçüm kanalıdır; korelasyon ölçülemeden
        # bağımsız sayılmazlar (zaten tek aile sayılırlar).
        independence: IndependenceAssessment
        if len(family_signals) >= 2:
            families, independence = _assess_independence(
                family_signals, baseline, correlation_cutoff, pool=_family_pool(baseline)
            )
        else:
            families, independence = family_signals, IndependenceAssessment(
                status="not_applicable",
                method="pearson_baseline_joint",
                reasons=("tek eksen; bağımsızlık iddiası kurulmadı",),
            )

        if len(families) < min_families:
            reason = f"window {window_start.date()}: bağımsız eksen {len(families)} < {min_families}"
            if dropped:
                reason += f"; düşürülen kayıtlar: {', '.join(dropped)}"
            analysis.reasons.append(reason)
            continue

        confounded_axes = tuple(
            axis
            for axis in LIFE_AXES
            if any(sig.startswith(f"{axis}.") for sig in families.get(axis, ()))
        )
        cluster = RuptureCluster(
            window_start=window_start,
            window_end=min(window_end, horizon) if horizon > window_start else window_end,
            families=families,
            persistence_records={episode.signal_id: episode.persistence for episode in kept},
            independence=independence,
            medium_change=medium_change
            or MediumChangeAssessment(
                status="unknown",
                baseline_rate=None,
                comparison_rate=None,
                delta=None,
                threshold=0.0,
                baseline_sample_size=0,
                comparison_sample_size=0,
                reasons=("üretim biçimi değerlendirmesi verilmedi",),
            ),
            confounded_axes=confounded_axes,
            dropped=tuple(sorted(dropped)),
            candidate_signal_count=len(kept),
        )
        analysis.candidates.append(cluster)

    if not analysis.candidates:
        return analysis

    analysis.candidates.sort(
        key=lambda cluster: (
            -int(cluster.is_verified),
            -cluster.family_count,
            -cluster.persistence_days,
            cluster.window_start,
        )
    )
    analysis.best = analysis.candidates[0]
    if not analysis.best.independence.is_confirmed:
        analysis.unknowns.append(
            "küme adayı var ama bağımsızlık doğrulanmadı; kesin küme sayılmadı"
        )
    return analysis
