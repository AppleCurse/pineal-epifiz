"""Üretim biçimi değişimi — karıştırıcı etkenin ölçümü.

Sözleşme #7/#8/#9:
    * oran YÜKSEK ama SABİT → confound DEĞİL,
    * oranda DÖNEMSEL değişim → yalnız etkilenen eksenler confounded,
    * örneklem yetersiz → ``unknown``; "confounded değil" ÇIKARILAMAZ.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_core.lifecycle.baseline_builder import SignalObservation
from agent_core.lifecycle.medium_change import (
    MEDIUM_CHANGE_SIGNAL,
    assess_medium_change,
    rate_in_window,
)

T0 = datetime(2022, 1, 1, tzinfo=timezone.utc)
BASE_END = T0 + timedelta(days=180)
CMP_START = T0 + timedelta(days=200)
CMP_END = T0 + timedelta(days=400)


def _obs(day: int, value: float) -> SignalObservation:
    return SignalObservation(MEDIUM_CHANGE_SIGNAL, T0 + timedelta(days=day), value, f"m:{day}")


def _series(baseline_value: float, comparison_value: float, n: int = 6) -> list[SignalObservation]:
    baseline = [_obs(10 * index, baseline_value) for index in range(n)]
    comparison = [_obs(200 + 10 * index, comparison_value) for index in range(n)]
    return baseline + comparison


def test_low_to_high_is_a_change() -> None:
    assessment = assess_medium_change(
        _series(0.0, 1.0), T0, BASE_END, CMP_START, CMP_END
    )
    assert assessment.status == "changed"
    assert assessment.is_shifted is True
    assert assessment.delta == 1.0


def test_high_but_stable_is_not_a_change() -> None:
    """Sözleşme #7: hep kurgu üreten hesap "değişti" diye işaretlenmez."""
    assessment = assess_medium_change(
        _series(1.0, 1.0), T0, BASE_END, CMP_START, CMP_END
    )
    assert assessment.status == "stable"
    assert assessment.is_shifted is False
    assert assessment.baseline_rate == 1.0 and assessment.comparison_rate == 1.0
    assert any("tek başına confound değildir" in reason for reason in assessment.reasons)


def test_change_downwards_also_counts() -> None:
    """Kurgudan ham çekime dönüş de karşılaştırılabilirliği bozar."""
    assessment = assess_medium_change(
        _series(1.0, 0.0), T0, BASE_END, CMP_START, CMP_END
    )
    assert assessment.status == "changed"
    assert assessment.delta == -1.0


def test_missing_baseline_sample_is_unknown_not_false() -> None:
    """Sözleşme #9: ölçülemeyen durum "confound yok" DEĞİLDİR."""
    observations = [_obs(200 + 10 * index, 1.0) for index in range(6)]  # baseline YOK
    assessment = assess_medium_change(observations, T0, BASE_END, CMP_START, CMP_END)

    assert assessment.status == "unknown"
    assert assessment.is_shifted is False
    assert assessment.delta is None
    assert any("baseline" in reason for reason in assessment.reasons)


def test_missing_comparison_sample_is_unknown() -> None:
    observations = [_obs(10 * index, 0.0) for index in range(6)]
    assessment = assess_medium_change(observations, T0, BASE_END, CMP_START, CMP_END)
    assert assessment.status == "unknown"
    assert assessment.comparison_sample_size == 0


def test_small_sample_is_unknown() -> None:
    assessment = assess_medium_change(_series(0.0, 1.0, n=3), T0, BASE_END, CMP_START, CMP_END)
    assert assessment.status == "unknown"
    assert assessment.baseline_sample_size == 3


def test_threshold_is_configurable_and_reported() -> None:
    data = _series(0.0, 0.4)
    strict = assess_medium_change(data, T0, BASE_END, CMP_START, CMP_END, threshold=0.25)
    relaxed = assess_medium_change(data, T0, BASE_END, CMP_START, CMP_END, threshold=0.5)

    assert strict.status == "changed"
    assert relaxed.status == "stable"
    assert strict.threshold == 0.25 and relaxed.threshold == 0.5
    assert strict.to_dict()["threshold"] == 0.25


def test_rate_in_window_reports_none_when_unmeasured() -> None:
    rate, count = rate_in_window([_obs(10, 1.0)], T0 + timedelta(days=500), T0 + timedelta(days=600))
    assert rate is None and count == 0


def test_assessment_is_serializable_for_the_report() -> None:
    payload = assess_medium_change(_series(0.0, 1.0), T0, BASE_END, CMP_START, CMP_END).to_dict()
    assert set(payload) >= {
        "status", "baseline_rate", "comparison_rate", "delta", "threshold",
        "baseline_sample_size", "comparison_sample_size", "reasons",
    }
