"""Küme analizi — tek sapma gürültü, iki sapma tesadüf, üç EKSEN desen.

Kurallar (hepsi testlidir):
    * **Kalıcılık**: bir sinyalin sapması ``min_persistence_days`` boyunca
      sürmezse küme kanıtı sayılmaz (tek günlük kayma değildir).
    * **Rebound**: sapma pencereden sonra normale döndüyse (geri sıçrama)
      kayıt düşürülür — "kalıcı" iddiası veriyle çürütülür.
    * **Bağımsızlık**: aynı ölçüm kanalından gelen sinyaller tek eksen sayılır
      (bkz. ``families``); ayrıca baseline korelasyonu yüksek (|r| ≥ eşik)
      aileler birleştirilir. Aksi hâlde "7 bağımsız sinyal" iddiası, tek
      hareketin 7 gölgesini saymak olurdu.
    * **Uç-nokta yasağı**: küme TÜM seri üzerinde aranır, ilk N ile son M
      karşılaştırılmaz. Pencere kaydırmalı taranır.

Bu modül "neden" sorusuna cevap vermez; yalnız "hangi pencerede kaç bağımsız
eksen kalıcı olarak saptı" sorusunu sayar.

Tüketici: ``agent_core.lifecycle.pipeline``.
Test: ``tests/lifecycle/test_lifecycle_cluster_analyzer.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence

from agent_core.lifecycle.baseline_builder import BaselineProfile, SignalObservation
from agent_core.lifecycle.deviation_detector import (
    MEDIUM_SHIFT_THRESHOLD,
    DeviationFinding,
    medium_shift_rate,
)
from agent_core.lifecycle.families import LIFE_AXES

__all__ = [
    "ClusterAnalysis",
    "RuptureCluster",
    "analyze_clusters",
    "DEFAULT_CLUSTER_WINDOW_DAYS",
    "DEFAULT_MIN_FAMILIES",
    "DEFAULT_MIN_PERSISTENCE_DAYS",
]

DEFAULT_CLUSTER_WINDOW_DAYS = 180
DEFAULT_MIN_FAMILIES = 3
DEFAULT_MIN_PERSISTENCE_DAYS = 60
DEFAULT_CORRELATION_CUTOFF = 0.8


@dataclass(frozen=True)
class SignalEpisode:
    """Tek bir sinyalin sapma dönemi."""

    signal_id: str
    family: str
    first_seen: datetime
    last_seen: datetime
    deviation_count: int

    @property
    def persistence_days(self) -> float:
        return (self.last_seen - self.first_seen).total_seconds() / 86400.0


@dataclass(frozen=True)
class RuptureCluster:
    """Aynı pencerede kümeleşen kalıcı sapmalar."""

    window_start: datetime
    window_end: datetime
    families: dict[str, tuple[str, ...]]
    persistence_days: float
    medium_shift_rate: Optional[float]
    confounded_axes: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()

    @property
    def family_count(self) -> int:
        return len(self.families)

    @property
    def signal_count(self) -> int:
        return sum(len(signals) for signals in self.families.values())

    @property
    def is_confounded(self) -> bool:
        """Üretim biçimi değişimi ile yaşam eksenleri aynı pencerede mi?"""
        if self.medium_shift_rate is None or self.medium_shift_rate <= MEDIUM_SHIFT_THRESHOLD:
            return False
        return bool(self.confounded_axes)


@dataclass
class ClusterAnalysis:
    """Küme taramasının sonucu (en iyi küme + neden bulunamadıysa gerekçeler)."""

    best: Optional[RuptureCluster] = None
    candidates: list[RuptureCluster] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _episodes(findings: Sequence[DeviationFinding]) -> list[SignalEpisode]:
    grouped: dict[str, list[DeviationFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.signal_id, []).append(finding)

    episodes: list[SignalEpisode] = []
    for signal_id, items in grouped.items():
        timestamps = sorted(finding.timestamp for finding in items)
        episodes.append(
            SignalEpisode(
                signal_id=signal_id,
                family=items[0].family,
                first_seen=timestamps[0],
                last_seen=timestamps[-1],
                deviation_count=len(items),
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


def _merge_correlated_families(
    families: dict[str, tuple[str, ...]],
    baseline: BaselineProfile,
    cutoff: float,
) -> dict[str, tuple[str, ...]]:
    """|r| ≥ eşik olan aileleri tek eksende birleştirir (bağımsızlık koruması)."""
    names = list(families)
    parent = {name: name for name in names}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            correlated = False
            for sig_left in families[left]:
                for sig_right in families[right]:
                    corr = baseline.correlation_between(sig_left, sig_right)
                    if corr is not None and abs(corr) >= cutoff:
                        correlated = True
                        break
                if correlated:
                    break
            if correlated:
                parent[find(right)] = find(left)

    merged: dict[str, list[str]] = {}
    for name in names:
        merged.setdefault(find(name), []).extend(families[name])

    return {root: tuple(sorted(set(signals))) for root, signals in sorted(merged.items())}


def analyze_clusters(
    findings: Sequence[DeviationFinding],
    observations: Sequence[SignalObservation],
    baseline: BaselineProfile,
    *,
    window_days: int = DEFAULT_CLUSTER_WINDOW_DAYS,
    min_families: int = DEFAULT_MIN_FAMILIES,
    min_persistence_days: int = DEFAULT_MIN_PERSISTENCE_DAYS,
    correlation_cutoff: float = DEFAULT_CORRELATION_CUTOFF,
) -> ClusterAnalysis:
    """Kaydırmalı pencerelerle kalıcı, bağımsız, eşzamanlı sapma kümesi arar."""
    analysis = ClusterAnalysis()
    episodes = _episodes(findings)
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
            if episode.persistence_days < min_persistence_days:
                dropped.append(f"{episode.signal_id}:persistence<{min_persistence_days}d")
                continue
            if _rebounded(baseline, observations, episode, window_end + timedelta(days=window_days)):
                dropped.append(f"{episode.signal_id}:rebound")
                continue
            kept.append(episode)

        if not kept:
            continue

        grouped: dict[str, list[str]] = {}
        for episode in kept:
            grouped.setdefault(episode.family, []).append(episode.signal_id)

        families = _merge_correlated_families(
            {family: tuple(sorted(signals)) for family, signals in grouped.items()},
            baseline,
            correlation_cutoff,
        )
        if len(families) < min_families:
            reason = f"window {window_start.date()}: bağımsız eksen {len(families)} < {min_families}"
            if dropped:
                # Düşürme gerekçesi kaybolmaz: "neden küme yok" sorusunun cevabı budur.
                reason += f"; düşürülen kayıtlar: {', '.join(dropped)}"
            analysis.reasons.append(reason)
            continue

        confounded_axes = tuple(
            axis for axis in LIFE_AXES if any(sig.startswith(f"{axis}.") for sig in families.get(axis, ()))
        )
        cluster = RuptureCluster(
            window_start=window_start,
            window_end=min(window_end, horizon) if horizon > window_start else window_end,
            families=families,
            persistence_days=max(episode.persistence_days for episode in kept),
            medium_shift_rate=medium_shift_rate(observations, window_start, window_end),
            confounded_axes=confounded_axes,
            dropped=tuple(sorted(dropped)),
        )
        analysis.candidates.append(cluster)

    if not analysis.candidates:
        return analysis

    analysis.candidates.sort(
        key=lambda cluster: (-cluster.family_count, -cluster.persistence_days, cluster.window_start)
    )
    analysis.best = analysis.candidates[0]
    return analysis
