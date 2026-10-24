"""Kalıcılık ölçümü — "iki uç nokta" yanılsamasının kilidi.

Sözleşme §7 ve kabul testleri #3: ilk ve son sapma arasındaki takvim süresi
tek başına kalıcılık DEĞİLDİR. Ölçülen şey dilim kapsaması, kesintisizlik ve
gözlem boşluğudur.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_core.lifecycle.baseline_builder import SignalObservation
from agent_core.lifecycle.persistence import (
    DEFAULT_PERSISTENCE_CONFIG,
    PersistenceConfig,
    measure_persistence,
)

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _obs(day: int, value: float = 0.0) -> SignalObservation:
    return SignalObservation("timing.is_night_post", T0 + timedelta(days=day), value, f"p:{day}")


def _weekly(days: list[int]) -> list[SignalObservation]:
    return [_obs(day) for day in days]


def test_continuous_weekly_deviation_is_persistent() -> None:
    days = [7 * index for index in range(11)]
    observations = _weekly(days)
    record = measure_persistence(observations, [obs.timestamp for obs in observations])

    assert record.status == "persistent"
    assert record.consecutive_deviation_windows == 11
    assert record.coverage_rate == 1.0
    assert record.longest_unobserved_gap_days == 7.0
    assert record.persistence_days >= 60


def test_two_endpoints_are_not_persistence() -> None:
    """1 Ocak + 5 Mart, arada hiçbir gözlem yok → kalıcılık KANITLANAMAZ."""
    observations = _weekly([0, 70])
    record = measure_persistence(observations, [obs.timestamp for obs in observations])

    assert record.status == "insufficient_coverage"
    assert record.consecutive_deviation_windows == 1
    assert record.coverage_rate is not None and record.coverage_rate < 0.5
    assert record.persistence_days >= 60  # takvim süresi VAR ama kanıt YOK
    assert any("kapsama" in reason for reason in record.reasons)


def test_long_silence_breaks_continuity() -> None:
    """60 günü aşan sessizlik sürekliliği keser (kapsama yüksek olsa bile)."""
    # Kapsama yeterli (0.65) ama 14. ile 64. gün arasında 50 gün sessizlik var.
    days = [0, 7, 14, 64, 71, 78, 85, 92, 99, 106, 113]
    observations = _weekly(days)
    record = measure_persistence(
        observations,
        [obs.timestamp for obs in observations],
        config=PersistenceConfig(max_unobserved_gap_days=45.0, min_span_days=60),
    )

    assert record.coverage_rate is not None and record.coverage_rate >= 0.5
    assert record.status == "insufficient_coverage"
    assert record.longest_unobserved_gap_days == 50.0
    assert any("boşluğu" in reason for reason in record.reasons)


def test_intermittent_deviation_is_not_persistent() -> None:
    days = [7 * index for index in range(13)]
    observations = _weekly(days)
    deviations = [observations[index].timestamp for index in range(0, 13, 4)]

    record = measure_persistence(observations, deviations)

    assert record.status == "intermittent"
    assert record.consecutive_deviation_windows == 1
    assert record.coverage_rate == 1.0  # gözlem tam, süreklilik yok


def test_short_span_is_transient() -> None:
    observations = _weekly([0, 7, 14])
    record = measure_persistence(observations, [obs.timestamp for obs in observations])

    assert record.status == "transient"
    assert record.persistence_days is not None and record.persistence_days < 60
    assert any("iki uç nokta" in reason for reason in record.reasons)


def test_missing_answers_are_not_treated_as_no_deviation() -> None:
    """Sözleşme §7: ``not_measurable`` dilim "sapma yok" sayılmaz."""
    # Yayılım 63 gün, ama 10 dilimin yalnız 3'ünde gözlem var: kapsama 0.30.
    sparse = _weekly([0, 30, 63])
    record = measure_persistence(sparse, [obs.timestamp for obs in sparse])

    assert record.coverage_rate is not None and record.coverage_rate < 0.5
    assert record.status == "insufficient_coverage"
    assert any("gözlenmeyen dilimler" in reason for reason in record.reasons)


def test_no_observation_is_explicitly_insufficient() -> None:
    record = measure_persistence([], [])
    assert record.status == "insufficient_coverage"
    assert record.coverage_rate is None
    assert record.persistence_days is None
    assert record.measurable_observation_count == 0


def test_no_deviation_is_transient() -> None:
    observations = _weekly([7 * index for index in range(11)])
    record = measure_persistence(observations, [])
    assert record.status == "transient"
    assert record.deviating_windows == 0


def test_config_is_reported_with_the_record() -> None:
    """Eşikler kodda gizli kalmaz; rapora yazılır."""
    observations = _weekly([7 * index for index in range(11)])
    record = measure_persistence(observations, [obs.timestamp for obs in observations])

    assert record.config["bucket_days"] == DEFAULT_PERSISTENCE_CONFIG.bucket_days
    assert record.config["min_consecutive_windows"] == 3
    assert record.config["min_span_days"] == 60
    assert set(record.to_dict()) >= {
        "status", "coverage_rate", "consecutive_deviation_windows",
        "longest_unobserved_gap_days", "persistence_days", "config", "reasons",
    }


def test_custom_config_changes_verdict_deterministically() -> None:
    """Eşik yapılandırılabilir: aynı veri, farklı ürün kararı — ama gerekçe yazılı."""
    observations = _weekly([0, 7, 14, 21])
    strict = measure_persistence(
        observations,
        [obs.timestamp for obs in observations],
        config=PersistenceConfig(min_consecutive_windows=5, min_span_days=21),
    )
    relaxed = measure_persistence(
        observations,
        [obs.timestamp for obs in observations],
        config=PersistenceConfig(min_consecutive_windows=3, min_span_days=21),
    )

    assert strict.status == "intermittent"
    assert relaxed.status == "persistent"
