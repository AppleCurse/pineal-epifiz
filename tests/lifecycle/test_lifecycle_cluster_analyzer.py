"""Küme analizi — kalıcılık, bağımsızlık ve confound kurallarının kilidi.

Üç yanlış burada kapatılır:
    * **iki uç nokta kalıcılık değildir** (arada gözlem yoksa "60 gün sürdü"
      denemez),
    * **ölçülemeyen bağımsızlık bağımsızlık değildir** (korelasyon yoksa küme
      "doğrulandı" sayılmaz, aday kalır),
    * **yüksek ama sabit kurgu oranı confound değildir** (karşılaştırma
      kişinin kendi baseline'ı ile yapılır).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from agent_core.lifecycle.baseline_builder import (
    BaselineProfile,
    SignalBaseline,
    SignalObservation,
)
from agent_core.lifecycle.cluster_analyzer import analyze_clusters
from agent_core.lifecycle.deviation_detector import DeviationFinding
from agent_core.lifecycle.families import signal_family
from agent_core.lifecycle.medium_change import MediumChangeAssessment

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _baseline(signal_ids: list[str], center: float = 1.0, correlation: bool = True) -> BaselineProfile:
    baselines = {
        signal_id: SignalBaseline(
            signal_id=signal_id,
            kind="binary",
            center=center,
            spread=0.0,
            n=10,
            min_value=center,
            max_value=center,
            is_reliable=True,
            is_constant=True,
            min_meaningful_delta=0.5,
            circular_period=None,
            window_start=T0 - timedelta(days=200),
            window_end=T0,
        )
        for signal_id in signal_ids
    }
    ordered = tuple(sorted(signal_ids))
    matrix = np.eye(len(ordered)) if correlation else None
    return BaselineProfile(
        subject_id="synthetic",
        baseline_window=(T0 - timedelta(days=200), T0),
        baselines=baselines,
        signal_order=ordered,
        signal_correlation=matrix,
    )


def _weekly_episode(
    baseline: BaselineProfile,
    signal_id: str,
    weeks: int = 11,
    value: float = 0.0,
    start_day: int = 0,
    observations: list[SignalObservation] | None = None,
    findings: list[DeviationFinding] | None = None,
) -> tuple[list[DeviationFinding], list[SignalObservation]]:
    """Haftalık, KESİNTİSİZ sapma serisi (gerçek kalıcılık)."""
    findings = findings if findings is not None else []
    observations = observations if observations is not None else []
    for index in range(weeks):
        moment = T0 + timedelta(days=start_day + 7 * index)
        observation = SignalObservation(signal_id, moment, value, f"{signal_id}:{index}")
        observations.append(observation)
        findings.append(DeviationFinding(observation, baseline.evaluate(observation), signal_family(signal_id)))
    return findings, observations


def _medium(status: str = "stable", delta: float = 0.0) -> MediumChangeAssessment:
    return MediumChangeAssessment(
        status=status,
        baseline_rate=0.0,
        comparison_rate=0.0 if status == "stable" else 1.0,
        delta=delta,
        threshold=0.25,
        baseline_sample_size=13,
        comparison_sample_size=13,
        reasons=(f"synthetic {status}",),
    )


SIGNALS = [
    "timing.is_night_post",
    "text.future_agency_density",
    "ritual.obj.kitchen_table",
    "habitat.is_daylight",
    "gaze.ear_mean",
]


def test_three_persistent_families_form_verified_cluster() -> None:
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"):
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is not None
    assert analysis.best.family_count == 3
    assert set(analysis.best.families) == {"timing", "text", "ritual"}
    assert analysis.best.independence.status == "confirmed"
    assert analysis.best.is_verified is True  # bağımsızlık ölçüldü ve eşiğin altında
    assert analysis.best.persistence_days >= 60
    assert analysis.best.confirmed_independent_signal_count == 3


def test_two_families_are_not_enough() -> None:
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density"):
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is None
    assert any("bağımsız eksen" in reason for reason in analysis.reasons)


def test_two_endpoints_are_not_persistence() -> None:
    """İlk ve son sapma 70 gün ayrı ama arada gözlem yok → kalıcılık YOK."""
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"):
        for day in (0, 70):
            moment = T0 + timedelta(days=day)
            observation = SignalObservation(signal_id, moment, 0.0, f"{signal_id}:{day}")
            observations.append(observation)
            findings.append(
                DeviationFinding(observation, baseline.evaluate(observation), signal_family(signal_id))
            )

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is None
    assert any("insufficient_coverage" in unknown for unknown in analysis.unknowns)
    assert any("insufficient_coverage" in reason for reason in analysis.reasons)


def test_single_shot_deviation_is_not_persistent() -> None:
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"):
        _weekly_episode(baseline, signal_id, weeks=1, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )
    assert analysis.best is None


def test_intermittent_deviation_is_not_persistent() -> None:
    """Her ay bir hafta sapma: süreklilik yok → 'persistent' denemez."""
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"):
        for index in range(11):
            moment = T0 + timedelta(days=7 * index)
            observation = SignalObservation(signal_id, moment, 0.0, f"{signal_id}:{index}")
            observations.append(observation)
            if index % 4 == 0:  # her 4. hafta sapma, arada dönüş
                findings.append(
                    DeviationFinding(observation, baseline.evaluate(observation), signal_family(signal_id))
                )

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is None
    assert any("persistence=" in reason for reason in analysis.reasons)


def test_rebound_removes_signal_from_cluster() -> None:
    """Sapma pencereden sonra normale dönerse "kalıcı" iddiası düşürülür."""
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"):
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    observations.append(
        SignalObservation("ritual.obj.kitchen_table", T0 + timedelta(days=180), 1.0, "rebound")
    )

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=120, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is None or "ritual" not in analysis.best.families
    assert any("rebound" in reason for reason in analysis.reasons) or analysis.best is None


def test_same_family_signals_count_once() -> None:
    """Bir hareketin üç gölgesi üç bağımsız eksen DEĞİLDİR."""
    signals = SIGNALS + ["gaze.head_pitch", "gaze.duchenne_contraction"]
    baseline = _baseline(signals)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("gaze.ear_mean", "gaze.head_pitch", "gaze.duchenne_contraction"):
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )
    assert analysis.best is None


def test_correlated_families_are_merged() -> None:
    """Baseline'da |r| ≥ eşik olan iki aile tek eksen sayılır."""
    signals = ["timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"]
    baseline = _baseline(signals)
    baseline.signal_correlation = np.array([[1.0, 0.95, 0.0], [0.95, 1.0, 0.0], [0.0, 0.0, 1.0]])

    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in signals:
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is None  # timing+text birleşti → 2 eksen
    assert any("bağımsız eksen" in reason for reason in analysis.reasons)


def test_unknown_correlation_blocks_confirmation() -> None:
    """Korelasyon ÖLÇÜLEMEDİYSE sinyaller bağımsız sayılmaz: sonuç aday kalır."""
    baseline = _baseline(SIGNALS, correlation=False)  # matris YOK
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"):
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is not None
    assert analysis.best.independence.status == "unknown"
    assert analysis.best.is_verified is False
    assert analysis.best.confirmed_independent_signal_count == 0  # 3 iddiası YOK
    assert any("bağımsızlık" in unknown for unknown in analysis.unknowns)


def test_medium_shift_with_life_axes_marks_confounded() -> None:
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("ritual.obj.kitchen_table", "timing.is_night_post", "text.future_agency_density"):
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings,
        observations,
        baseline,
        window_days=180,
        min_persistence_days=60,
        medium_change=_medium("changed", delta=1.0),
    )

    assert analysis.best is not None
    assert analysis.best.is_confounded is True
    assert "ritual" in analysis.best.confounded_axes
    assert analysis.best.is_verified is False  # confound → kesin küme değil


def test_stable_high_authored_rate_is_not_confounded() -> None:
    """Oran YÜKSEK ama SABİT: confound değil (eski %50 kuralının yanlışı)."""
    baseline = _baseline(SIGNALS)
    findings: list[DeviationFinding] = []
    observations: list[SignalObservation] = []
    for signal_id in ("ritual.obj.kitchen_table", "timing.is_night_post", "text.future_agency_density"):
        _weekly_episode(baseline, signal_id, findings=findings, observations=observations)

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=180, min_persistence_days=60, medium_change=_medium()
    )

    assert analysis.best is not None
    assert analysis.best.is_confounded is False
    assert analysis.best.is_verified is True


def test_no_findings_no_cluster() -> None:
    baseline = _baseline(SIGNALS)
    analysis = analyze_clusters([], [], baseline, medium_change=_medium())
    assert analysis.best is None
    assert any("no_deviation" in reason for reason in analysis.reasons)
    assert analysis.persistence_config["bucket_days"] == 7  # eşikler rapora yazılır
