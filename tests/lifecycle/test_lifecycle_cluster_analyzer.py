"""Küme analizi — kalıcılık, geri sıçrama ve BAĞIMSIZLIK kurallarının kilidi."""

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

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _baseline(signal_ids: list[str], center: float = 1.0) -> BaselineProfile:
    """Sabit baseline: her sinyal baseline penceresinde hep ``center``."""
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
    return BaselineProfile(
        subject_id="synthetic",
        baseline_window=(T0 - timedelta(days=200), T0),
        baselines=baselines,
        signal_order=tuple(signal_ids),
    )


def _finding(baseline: BaselineProfile, signal_id: str, day: int, value: float = 0.0) -> DeviationFinding:
    observation = SignalObservation(signal_id, T0 + timedelta(days=day), value, f"{signal_id}:{day}")
    return DeviationFinding(observation, baseline.evaluate(observation), signal_family(signal_id))


def _observations(findings: list[DeviationFinding]) -> list[SignalObservation]:
    return [finding.observation for finding in findings]


SIGNALS = [
    "timing.is_night_post",
    "text.future_agency_density",
    "ritual.obj.kitchen_table",
    "habitat.is_daylight",
    "gaze.ear_mean",
]


def test_three_persistent_families_form_cluster() -> None:
    baseline = _baseline(SIGNALS)
    findings = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"):
        findings.append(_finding(baseline, signal_id, 0))
        findings.append(_finding(baseline, signal_id, 40))

    analysis = analyze_clusters(
        findings,
        _observations(findings),
        baseline,
        window_days=120,
        min_families=3,
        min_persistence_days=30,
    )

    assert analysis.best is not None
    assert analysis.best.family_count == 3
    assert set(analysis.best.families) == {"timing", "text", "ritual"}
    assert analysis.best.persistence_days == 40.0


def test_two_families_are_not_enough() -> None:
    baseline = _baseline(SIGNALS)
    findings = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density"):
        findings.append(_finding(baseline, signal_id, 0))
        findings.append(_finding(baseline, signal_id, 40))

    analysis = analyze_clusters(
        findings, _observations(findings), baseline, window_days=120, min_persistence_days=30
    )

    assert analysis.best is None
    assert any("bağımsız eksen" in reason for reason in analysis.reasons)


def test_single_shot_deviation_is_not_persistent() -> None:
    baseline = _baseline(SIGNALS)
    findings = [
        _finding(baseline, signal_id, 0)
        for signal_id in ("timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table")
    ]

    analysis = analyze_clusters(
        findings, _observations(findings), baseline, window_days=120, min_persistence_days=30
    )

    assert analysis.best is None


def test_rebound_removes_signal_from_cluster() -> None:
    """Sapma pencereden sonra normale dönerse "kalıcı" iddiası düşürülür."""
    baseline = _baseline(SIGNALS)
    findings = []
    for signal_id in ("timing.is_night_post", "text.future_agency_density"):
        findings.append(_finding(baseline, signal_id, 0))
        findings.append(_finding(baseline, signal_id, 40))
    findings.append(_finding(baseline, "ritual.obj.kitchen_table", 0))
    findings.append(_finding(baseline, "ritual.obj.kitchen_table", 40))

    # Ritüel 90. günde geri döndü (baseline değeri 1.0 → sapma değil).
    observations = _observations(findings) + [
        SignalObservation("ritual.obj.kitchen_table", T0 + timedelta(days=90), 1.0, "rebound")
    ]

    analysis = analyze_clusters(
        findings, observations, baseline, window_days=120, min_persistence_days=30
    )

    assert analysis.best is None
    assert any("rebound" in reason for reason in analysis.reasons)


def test_same_family_signals_count_once() -> None:
    """Bir hareketin üç gölgesi üç bağımsız eksen DEĞİLDİR."""
    baseline = _baseline(SIGNALS + ["gaze.head_pitch", "gaze.duchenne_contraction"])
    findings = []
    for signal_id in ("gaze.ear_mean", "gaze.head_pitch", "gaze.duchenne_contraction"):
        findings.append(_finding(baseline, signal_id, 0))
        findings.append(_finding(baseline, signal_id, 40))

    analysis = analyze_clusters(
        findings, _observations(findings), baseline, window_days=120, min_persistence_days=30
    )

    assert analysis.best is None


def test_correlated_families_are_merged() -> None:
    """Baseline'da |r| ≥ eşik olan iki aile tek eksen sayılır."""
    signals = ["timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"]
    baseline = _baseline(signals)
    baseline.signal_correlation = np.array([[1.0, 0.95, 0.0], [0.95, 1.0, 0.0], [0.0, 0.0, 1.0]])

    findings = []
    for signal_id in signals:
        findings.append(_finding(baseline, signal_id, 0))
        findings.append(_finding(baseline, signal_id, 40))

    analysis = analyze_clusters(
        findings, _observations(findings), baseline, window_days=120, min_persistence_days=30
    )

    assert analysis.best is None  # timing+text birleşti → 2 eksen


def test_medium_shift_with_life_axes_marks_confounded() -> None:
    baseline = _baseline(SIGNALS + ["media.is_authored_or_staged"], center=0.0)
    findings = []
    for signal_id in ("ritual.obj.kitchen_table", "timing.is_night_post"):
        findings.append(_finding(baseline, signal_id, 0))
        findings.append(_finding(baseline, signal_id, 40))
    # Üretim biçimi baseline'da 0.0; hedefte 1.0 (kurguya kayış).
    findings.append(_finding(baseline, "media.is_authored_or_staged", 0, value=1.0))
    findings.append(_finding(baseline, "media.is_authored_or_staged", 40, value=1.0))

    analysis = analyze_clusters(
        findings, _observations(findings), baseline, window_days=120, min_persistence_days=30
    )

    assert analysis.best is not None
    assert analysis.best.medium_shift_rate == 1.0
    assert analysis.best.is_confounded is True
    assert analysis.best.confounded_axes == ("ritual",)


def test_no_findings_no_cluster() -> None:
    baseline = _baseline(SIGNALS)
    analysis = analyze_clusters([], [], baseline)
    assert analysis.best is None
    assert any("no_deviation" in reason for reason in analysis.reasons)
