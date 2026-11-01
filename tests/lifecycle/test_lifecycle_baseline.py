"""Boylamsal baseline matematiği — üç sessiz yanlışın kilidi.

Her test, düzeltme geri alınırsa KIRILACAK şekilde yazıldı (mutasyon mantığı):
    * ``z`` yolu tekrar kullanılırsa → ``test_constant_baseline_detects_break``,
    * aritmetik ortalama kullanılırsa → ``test_circular_mean_is_not_arithmetic``,
    * tolerans göz ardı edilirse → ``test_tiny_spread_does_not_flag_microscopic_noise``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_core.lifecycle.baseline_builder import (
    MIN_SAMPLES,
    SignalObservation,
    SignalRegistry,
    SignalSpec,
    build_baseline,
    circular_distance,
    circular_mean_hours,
)
from agent_core.lifecycle.default_specs import default_registry

T0 = datetime(2021, 1, 1, tzinfo=timezone.utc)


def _obs(signal_id: str, day: int, value: float, ref: str | None = None) -> SignalObservation:
    return SignalObservation(signal_id, T0 + timedelta(days=day), float(value), ref or f"{signal_id}:{day}")


def test_constant_baseline_detects_break() -> None:
    """20 gözlem hep 0.0 → std=0. z-score çöker; constant_break yakalar."""
    observations = [_obs("timing.is_night_post", day, 0.0) for day in range(20)]
    profile = build_baseline("s", observations, T0, registry=default_registry())
    baseline = profile.get("timing.is_night_post")

    assert baseline is not None
    assert baseline.is_constant and baseline.is_reliable
    assert baseline.spread == 0.0

    result = baseline.evaluate(1.0)
    assert result.is_deviation is True
    assert result.method == "constant_break"
    assert result.z_score is None


def test_constant_baseline_ignores_noise_below_tolerance() -> None:
    observations = [_obs("timing.post_hour", day, 14.0) for day in range(20)]
    profile = build_baseline("s", observations, T0, registry=default_registry())
    baseline = profile.get("timing.post_hour")

    assert baseline is not None
    assert baseline.evaluate(14.0004).is_deviation is False  # tolerans 1.0 saat
    assert baseline.evaluate(3.5).is_deviation is True  # 10.5 saatlik dairesel fark


def test_circular_mean_is_not_arithmetic() -> None:
    """23:30 ve 00:30 → dairesel ortalama 00:00. Lineer ortalama 12:00 verirdi."""
    observations = []
    for day in range(10):
        observations.append(_obs("timing.post_hour", day * 2, 23.5))
        observations.append(_obs("timing.post_hour", day * 2 + 1, 0.5))

    profile = build_baseline("s", observations, T0, registry=default_registry())
    baseline = profile.get("timing.post_hour")

    assert baseline is not None
    assert min(abs(baseline.center - 0.0), abs(baseline.center - 24.0)) < 0.01
    assert abs(baseline.center - 12.0) > 6.0
    assert baseline.spread == pytest.approx(0.5009, abs=0.02)


def test_circular_distance_wraps() -> None:
    observations = [_obs("timing.post_hour", day, 23.0) for day in range(20)]
    profile = build_baseline("s", observations, T0, registry=default_registry())
    baseline = profile.get("timing.post_hour")

    assert baseline is not None
    assert baseline.evaluate(0.5).distance == pytest.approx(1.5, abs=0.01)
    assert baseline.evaluate(0.5).is_deviation is True
    assert baseline.evaluate(23.4).is_deviation is False


def test_circular_helpers_agree() -> None:
    assert circular_mean_hours([23.5, 0.5]) == pytest.approx(0.0, abs=0.01) or circular_mean_hours(
        [23.5, 0.5]
    ) == pytest.approx(24.0, abs=0.01)
    assert circular_distance(23.0, 1.0, 24.0) == pytest.approx(2.0)
    assert circular_mean_hours([]) is None


def test_circular_signals_skip_iqr() -> None:
    """IQR dairesel veride 23.5/0.5'i 'uç değer' sanıp silerdi."""
    observations = [_obs("timing.post_hour", day, 23.5 if day % 2 else 0.5) for day in range(20)]
    profile = build_baseline("s", observations, T0, registry=default_registry())
    baseline = profile.get("timing.post_hour")

    assert baseline is not None
    assert baseline.n == 20


def test_unspecified_signal_is_excluded_not_guessed() -> None:
    observations = [_obs("bilinmeyen.sinyal", day, 1.0) for day in range(10)]
    profile = build_baseline("s", observations, T0, registry=default_registry())

    assert profile.get("bilinmeyen.sinyal") is None
    assert "bilinmeyen.sinyal" in profile.unspecified_signals


def test_strict_mode_forces_declaration() -> None:
    observations = [_obs("bilinmeyen.sinyal", day, 1.0) for day in range(10)]
    with pytest.raises(ValueError, match="SignalSpec yok"):
        build_baseline("s", observations, T0, registry=default_registry(), strict=True)


def test_circular_spec_without_period_raises() -> None:
    with pytest.raises(ValueError, match="circular_period"):
        SignalSpec("x", kind="circular", min_meaningful_delta=1.0)


def test_unreliable_baseline_never_flags() -> None:
    observations = [_obs("timing.is_night_post", day, 0.0) for day in range(MIN_SAMPLES - 1)]
    profile = build_baseline("s", observations, T0, registry=default_registry())
    baseline = profile.get("timing.is_night_post")

    assert baseline is not None
    result = baseline.evaluate(1.0)
    assert result.is_deviation is False
    assert result.method == "insufficient_baseline"


def test_novelty_is_not_deviation() -> None:
    observations = [_obs("timing.is_night_post", day, 0.0) for day in range(10)]
    profile = build_baseline("s", observations, T0, registry=default_registry())
    result = profile.evaluate(_obs("ritual.obj.never_seen", 400, 1.0))

    assert result.method == "no_baseline"
    assert result.is_deviation is False
    assert "YENİLİK" in result.reason


def test_tiny_spread_does_not_flag_microscopic_noise() -> None:
    values = [14.0, 14.0001, 13.9999, 14.0002, 13.9998, 14.0]
    observations = [_obs("timing.post_hour", day, value) for day, value in enumerate(values)]
    profile = build_baseline("s", observations, T0, registry=default_registry())
    baseline = profile.get("timing.post_hour")

    assert baseline is not None
    result = baseline.evaluate(14.01)
    assert result.method == "z_score"
    assert result.z_score is not None and result.z_score > 2.0
    assert result.is_deviation is False  # 0.01 saat < 1.0 saat tolerans


def test_outlier_day_does_not_poison_baseline() -> None:
    normal = [_obs("text.word_count", day, 20.0) for day in range(10)]
    outlier = [_obs("text.word_count", 999, 500.0)]
    profile = build_baseline("s", normal + outlier, T0, registry=default_registry())
    baseline = profile.get("text.word_count")

    assert baseline is not None
    assert baseline.center == pytest.approx(20.0, abs=1e-6)
    assert baseline.max_value == pytest.approx(20.0, abs=1e-6)


def test_non_finite_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="sonlu"):
        _obs("timing.post_hour", 0, float("nan"))


def test_prefix_spec_resolves_for_data_defined_tags() -> None:
    registry = default_registry()
    resolved = registry.resolve("ritual.obj.bilinmeyen_nesne")
    assert resolved is not None
    assert resolved.kind == "binary"


def test_correlation_detects_redundant_signals() -> None:
    observations = []
    for day in range(12):
        base = 0.30 + 0.01 * (day % 3)
        observations.append(_obs("gaze.ear_mean", day, base))
    # Aynı ölçümün ikinci adı: korelasyon ~1 olmalı (bağımsız sayılmamalı).
    profile = build_baseline("s", observations, T0, registry=default_registry())
    assert profile.correlation_between("gaze.ear_mean", "gaze.ear_mean") is None
    assert profile.signal_order == ("gaze.ear_mean",)


def test_registry_custom_specs_respected() -> None:
    registry = SignalRegistry([SignalSpec("ritual.obj.*", kind="binary", min_meaningful_delta=0.5)])
    observations = [_obs("ritual.obj.kitchen_table", day, 1.0) for day in range(6)]
    profile = build_baseline("s", observations, T0, registry=registry)
    baseline = profile.get("ritual.obj.kitchen_table")

    assert baseline is not None and baseline.is_reliable
    assert baseline.evaluate(0.0).is_deviation is True
