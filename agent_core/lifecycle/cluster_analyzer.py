"""Cluster Analyzer - Independent Deviation Clustering Across Time Windows.

Sapmaları zaman pencerelerinde kümeler:
- Gerçek gözlem sürekliliği (iki uçtaki takvim süresi yetersiz; alt dilim dağılımı şart)
- Bağımsızlık doğrulaması (korelasyon bilinmiyorsa bağımsız sayılamaz; fail-closed)
- Üretim biçimi değişimi (baseline staged oranı ile hedef staged oranı farkı kıyaslanır)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

MIN_INDEPENDENT_SIGNALS = 3
CLUSTER_WINDOW_DAYS = 180
MIN_PERSISTENCE_DAYS = 60
MAX_CORRELATION = 0.5
MIN_SUB_WINDOWS = 3


@dataclass(frozen=True)
class DeviationEvent:
    signal_id: str
    timestamp: datetime
    value: float
    baseline_center: float
    distance: float
    method: str
    source_ref: str


@dataclass(frozen=True)
class SignalCluster:
    start: datetime
    end: datetime
    signals: Tuple[str, ...]
    event_count: int
    persistence_days: int
    continuity_ratio: float
    independence_verified: bool
    is_confounded: bool
    medium_change_status: str  # "stable" | "confounded" | "unknown"
    confounded_axes: Tuple[str, ...] = ()

    @property
    def signal_count(self) -> int:
        return len(self.signals)


class ClusterAnalyzer:
    def __init__(
        self,
        baseline_profile,
        window_days: int = CLUSTER_WINDOW_DAYS,
        min_persistence_days: int = MIN_PERSISTENCE_DAYS,
        max_correlation: float = MAX_CORRELATION,
    ) -> None:
        self.baseline = baseline_profile
        self.window_days = window_days
        self.min_persistence_days = min_persistence_days
        self.max_correlation = max_correlation

    def _independent_signals(
        self, signals: List[str]
    ) -> Tuple[List[str], bool]:
        """Korelasyon doğrulanmamışsa fail-closed: bağımsızlık onaylanamaz."""
        if not self.baseline.correlation_verified or self.baseline.signal_correlation is None:
            return signals, False

        order = self.baseline.signal_order
        corr_matrix = self.baseline.signal_correlation
        idx = {s: order.index(s) for s in signals if s in order}
        keep: List[str] = []

        for s in signals:
            if s not in idx:
                continue
            independent = True
            for k in keep:
                if k in idx and abs(corr_matrix[idx[s], idx[k]]) > self.max_correlation:
                    independent = False
                    break
            if independent:
                keep.append(s)

        return keep, True

    def _check_continuity(self, events: List[DeviationEvent]) -> Tuple[int, float, bool]:
        """İki uç arasındaki sürenin ötesinde; pencere içi dağılım ve devamlılığı ölçer."""
        if not events:
            return 0, 0.0, False

        timestamps = [e.timestamp for e in events]
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        span_days = max(1, (last_ts - first_ts).days)

        if span_days < self.min_persistence_days:
            return span_days, 0.0, False

        step = (last_ts - first_ts) / MIN_SUB_WINDOWS
        sub_window_hits = 0
        for i in range(MIN_SUB_WINDOWS):
            w_start = first_ts + step * i
            w_end = first_ts + step * (i + 1)
            if any(w_start <= ts <= w_end for ts in timestamps):
                sub_window_hits += 1

        continuity_ratio = sub_window_hits / MIN_SUB_WINDOWS
        is_continuous = (sub_window_hits == MIN_SUB_WINDOWS)
        return span_days, continuity_ratio, is_continuous

    def analyze(
        self,
        events: List[DeviationEvent],
        target_end: datetime,
        all_target_observations: Optional[List] = None,
    ) -> List[SignalCluster]:
        if not events:
            return []

        events = sorted(events, key=lambda e: e.timestamp)
        clusters: List[SignalCluster] = []
        used = set()

        for i, anchor in enumerate(events):
            if i in used:
                continue
            window_start = anchor.timestamp
            window_end = min(window_start + timedelta(days=self.window_days), target_end)

            in_window = [
                (j, e) for j, e in enumerate(events)
                if j not in used and window_start <= e.timestamp <= window_end
            ]
            if len(in_window) < MIN_INDEPENDENT_SIGNALS:
                continue

            raw_signals = sorted({e.signal_id for _, e in in_window})
            independent, indep_verified = self._independent_signals(raw_signals)

            if len(independent) < MIN_INDEPENDENT_SIGNALS:
                continue

            events_in_win = [e for _, e in in_window]
            span_days, continuity_ratio, is_continuous = self._check_continuity(events_in_win)

            if not is_continuous:
                continue

            # Üretim biçimi değişimi karşılaştırması (Baseline vs Target Staged Rate)
            target_staged_obs = []
            if all_target_observations:
                target_staged_obs = [
                    o.value for o in all_target_observations
                    if getattr(o, "signal_id", "") == "media.is_authored_or_staged"
                    and window_start <= o.timestamp <= window_end
                ]
            else:
                target_staged_obs = [e.value for e in events_in_win if e.signal_id == "media.is_authored_or_staged"]

            if self.baseline.staged_rate is None or len(target_staged_obs) == 0:
                medium_change_status = "unknown"
                is_confounded = False
            else:
                target_staged_rate = sum(target_staged_obs) / len(target_staged_obs)
                delta = target_staged_rate - self.baseline.staged_rate
                is_confounded = (delta > 0.4)
                medium_change_status = "confounded" if is_confounded else "stable"

            confounded_axes = tuple(s for s in independent if s.startswith(("visual.", "habitat.")))

            clusters.append(SignalCluster(
                start=window_start,
                end=window_end,
                signals=tuple(independent),
                event_count=len(in_window),
                persistence_days=span_days,
                continuity_ratio=continuity_ratio,
                independence_verified=indep_verified,
                is_confounded=is_confounded,
                medium_change_status=medium_change_status,
                confounded_axes=confounded_axes if is_confounded else (),
            ))
            used.update(j for j, _ in in_window)

        return clusters
