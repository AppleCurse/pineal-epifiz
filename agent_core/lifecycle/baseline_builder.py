"""Life Rupture Lifecycle - Signal Observation & Baseline Data Models.

Deterministik sinyal gözlemi ve taban çizgisi (baseline) veri yapıları.
Dairesel saat istatistiği, sabit baseline (std=0) toleransı ve bağımsızlık analizi içerir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class SignalObservation:
    """Tek bir tarihli sinyal ölçümü. Teşhis veya yorum içermez."""
    signal_id: str
    timestamp: datetime
    value: float
    source_ref: str = ""
    measurement_status: str = "measured"  # measured | partial | not_measurable | invalid
    signal_family: str = ""


@dataclass(frozen=True)
class SignalBaseline:
    """Bir sinyalin taban çizgisi (kişinin kendi geçmiş referansı)."""
    signal_id: str
    mean: float
    std: float
    sample_count: int
    is_constant: bool = False
    constant_value: Optional[float] = None
    meaningful_delta: float = 0.5
    is_circular: bool = False
    circular_period: float = 24.0

    def distance(self, val: float) -> float:
        if self.is_circular:
            diff = abs(val - self.mean) % self.circular_period
            return min(diff, self.circular_period - diff)
        return abs(val - self.mean)

    def z_score(self, val: float) -> float:
        if self.is_constant or self.std < 1e-9:
            return 0.0
        return (val - self.mean) / self.std

    def is_deviation(self, val: float, z_threshold: float = 2.0) -> bool:
        """std=0 durumunda sabit değerden meaningful_delta üzeri sapmadır; gürültü yok sayılır."""
        dist = self.distance(val)
        if self.is_constant or self.std < 1e-9:
            return dist > self.meaningful_delta
        return abs(self.z_score(val)) >= z_threshold


@dataclass(frozen=True)
class BaselineProfile:
    """Belirli bir zaman aralığında çıkarılan çok-sinyalli taban çizgisi."""
    subject_id: str
    window_start: datetime
    window_end: datetime
    baselines: Dict[str, SignalBaseline]
    signal_correlation: Optional[np.ndarray] = None
    signal_order: Tuple[str, ...] = field(default_factory=tuple)
    correlation_verified: bool = False
    staged_rate: Optional[float] = None
    staged_sample_count: int = 0


def _circular_mean_std(values: List[float], period: float = 24.0) -> Tuple[float, float]:
    """Birim vektör ayrışımı ile dairesel ortalama ve yayılım (23:30 + 00:30 -> ~gece yarısı)."""
    rads = [v * (2.0 * math.pi / period) for v in values]
    sin_sum = sum(math.sin(r) for r in rads)
    cos_sum = sum(math.cos(r) for r in rads)
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean_angle = math.atan2(sin_sum, cos_sum) % (2.0 * math.pi)
    mean_val = mean_angle * (period / (2.0 * math.pi))
    r = math.sqrt((sin_sum / n) ** 2 + (cos_sum / n) ** 2)
    # ponytail: R=1 için std=0; yaklaşık dairesel dispersiyon. Çoklu dağılım analizi gerektiğinde Von Mises eklenecek.
    circ_std = math.sqrt(max(0.0, -2.0 * math.log(max(r, 1e-12)))) * (period / (2.0 * math.pi))
    return float(mean_val), float(circ_std)


def build_baseline(
    subject_id: str,
    observations: List[SignalObservation],
    baseline_start: datetime,
    baseline_end: datetime,
    min_samples: int = 3,
) -> BaselineProfile:
    """Belirli bir zaman aralığındaki geçerli gözlemlerden deterministik taban çizgisi çıkarır."""
    grouped: Dict[str, List[float]] = {}
    time_series: Dict[str, Dict[datetime, float]] = {}

    staged_vals: List[float] = []
    for obs in observations:
        if obs.measurement_status in ("not_measurable", "invalid"):
            continue
        if baseline_start <= obs.timestamp <= baseline_end:
            grouped.setdefault(obs.signal_id, []).append(obs.value)
            time_series.setdefault(obs.signal_id, {})[obs.timestamp] = obs.value
            if obs.signal_id == "media.is_authored_or_staged":
                staged_vals.append(obs.value)

    baselines: Dict[str, SignalBaseline] = {}
    valid_signals = []

    for sid, vals in grouped.items():
        if len(vals) < min_samples:
            continue
        is_circ = sid.endswith((".post_hour", ".hour")) or "circular" in sid
        if is_circ:
            mean_val, std_val = _circular_mean_std(vals, 24.0)
            is_const = std_val < 1e-4
            meaningful_delta = 2.0
        else:
            arr = np.array(vals, dtype=float)
            mean_val = float(np.mean(arr))
            std_val = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
            is_const = std_val < 1e-9
            meaningful_delta = 0.5 if "is_" in sid or sid.startswith("binary.") else 0.1

        baselines[sid] = SignalBaseline(
            signal_id=sid,
            mean=mean_val,
            std=std_val,
            sample_count=len(vals),
            is_constant=is_const,
            constant_value=mean_val if is_const else None,
            meaningful_delta=meaningful_delta,
            is_circular=is_circ,
            circular_period=24.0,
        )
        valid_signals.append(sid)

    valid_signals.sort()
    n_sigs = len(valid_signals)
    corr_matrix = np.eye(n_sigs, dtype=float) if n_sigs > 0 else None
    corr_verified = False

    all_timestamps = sorted({
        obs.timestamp for obs in observations
        if obs.measurement_status not in ("not_measurable", "invalid")
        and baseline_start <= obs.timestamp <= baseline_end
    })

    # Yeterli ortak zaman noktası ve en az 2 varyanslı sinyal varsa korelasyon doğrulanabilir
    if n_sigs >= 2 and len(all_timestamps) >= max(min_samples, 5):
        variant_signals = [s for s in valid_signals if not baselines[s].is_constant]

        if len(variant_signals) >= 2:
            matrix = [
                [time_series[s].get(ts, baselines[s].mean) for ts in all_timestamps]
                for s in variant_signals
            ]
            with np.errstate(divide="ignore", invalid="ignore"):
                sub_corr = np.corrcoef(matrix)
                if not np.any(np.isnan(sub_corr)):
                    for i, s1 in enumerate(variant_signals):
                        idx1 = valid_signals.index(s1)
                        for j, s2 in enumerate(variant_signals):
                            idx2 = valid_signals.index(s2)
                            corr_matrix[idx1, idx2] = sub_corr[i, j]
                    corr_verified = True
        else:
            # Varyans yoksa korelasyon ölçülemez; bağımsızlık varsayılmaz (fail-closed)
            corr_verified = False

    mean_staged = float(np.mean(staged_vals)) if staged_vals else None

    return BaselineProfile(
        subject_id=subject_id,
        window_start=baseline_start,
        window_end=baseline_end,
        baselines=baselines,
        signal_correlation=corr_matrix,
        signal_order=tuple(valid_signals),
        correlation_verified=corr_verified,
        staged_rate=mean_staged,
        staged_sample_count=len(staged_vals),
    )
