"""Sapma dedektörü — deterministik kimlik, yokluk tipi, yapısal confound."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from agent_core.domain.evidence_models import EvidenceTimeline
from agent_core.lifecycle.baseline_builder import SignalObservation, build_baseline
from agent_core.lifecycle.default_specs import default_registry
from agent_core.lifecycle.deviation_detector import (
    MEDIUM_SIGNAL,
    build_evidence_timeline,
    detect_deviations,
    make_evidence_id,
    medium_shift_rate,
)

T0 = datetime(2022, 1, 1, tzinfo=timezone.utc)
EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{20}$")


def _obs(signal_id: str, day: int, value: float, ref: str | None = None) -> SignalObservation:
    return SignalObservation(signal_id, T0 + timedelta(days=day), float(value), ref or f"{signal_id}:{day}")


def _baseline():
    observations = (
        [_obs("timing.is_night_post", day, 0.0) for day in range(10)]
        + [_obs(MEDIUM_SIGNAL, day, 0.0) for day in range(10)]
        + [_obs("ritual.obj.kitchen_table", day, 1.0) for day in range(10)]
        + [_obs("habitat.is_daylight", day, 1.0) for day in range(10)]
    )
    return build_baseline("s", observations, T0, T0 + timedelta(days=200), registry=default_registry(), strict=True)


# --- Deterministik kimlik ---------------------------------------------------


def test_evidence_id_is_deterministic_across_runs() -> None:
    key = "timing.is_night_post|post_0001|2022-01-15T00:00:00+00:00|1|constant_break"
    first = make_evidence_id("life_rupture", "observed_at", key)
    second = make_evidence_id("life_rupture", "observed_at", key)

    assert first == second
    assert EVIDENCE_ID_RE.match(first)


def test_evidence_id_differs_for_different_observations() -> None:
    key_one = "timing.is_night_post|post_0001|2022-01-15T00:00:00+00:00|1|constant_break"
    key_two = "timing.is_night_post|post_0002|2022-01-16T00:00:00+00:00|1|constant_break"
    assert make_evidence_id("life_rupture", "observed_at", key_one) != make_evidence_id(
        "life_rupture", "observed_at", key_two
    )


def test_timeline_ids_are_stable_across_reruns() -> None:
    baseline = _baseline()
    target = [_obs("timing.is_night_post", 300, 1.0), _obs("ritual.obj.kitchen_table", 305, 0.0)]
    first = build_evidence_timeline(
        detect_deviations(baseline, target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    )
    second = build_evidence_timeline(
        detect_deviations(baseline, target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    )
    assert [entry.evidence_id for entry in first.entries] == [entry.evidence_id for entry in second.entries]


# --- Yokluk ≠ gözlem --------------------------------------------------------


def test_ritual_absence_is_epistemic_absence() -> None:
    baseline = _baseline()
    target = [_obs("ritual.obj.kitchen_table", 300, 0.0)]
    findings = detect_deviations(baseline, target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    timeline = build_evidence_timeline(findings)

    assert len(timeline.entries) == 1
    entry = timeline.entries[0]
    assert entry.epistemic_type == "absence"
    assert entry.scope["family"] == "ritual"
    assert entry.source_metrics["family"] == "ritual"
    assert entry.epistemic_note  # kanonik servisten gelir, boş bırakılmaz


def test_non_ritual_deviation_is_observation() -> None:
    baseline = _baseline()
    target = [_obs("timing.is_night_post", 300, 1.0)]
    timeline = build_evidence_timeline(
        detect_deviations(baseline, target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    )

    assert timeline.entries[0].epistemic_type == "observation"


# --- Confound yapısal -------------------------------------------------------


def _target_with_medium_shift() -> list[SignalObservation]:
    target = [
        _obs(MEDIUM_SIGNAL, 300, 1.0),
        _obs(MEDIUM_SIGNAL, 310, 1.0),
        _obs(MEDIUM_SIGNAL, 320, 1.0),
        _obs(MEDIUM_SIGNAL, 330, 1.0),
        _obs(MEDIUM_SIGNAL, 340, 0.0),  # oran 0.8
        _obs("ritual.obj.kitchen_table", 300, 0.0),
        _obs("habitat.is_daylight", 300, 0.0),
    ]
    return target


def _baseline_observations() -> list[SignalObservation]:
    return (
        [_obs("timing.is_night_post", day, 0.0) for day in range(10)]
        + [_obs(MEDIUM_SIGNAL, day, 0.0) for day in range(10)]
        + [_obs("ritual.obj.kitchen_table", day, 1.0) for day in range(10)]
        + [_obs("habitat.is_daylight", day, 1.0) for day in range(10)]
    )


def test_confound_flag_is_structural_not_text_appendix() -> None:
    """Confound KARŞILAŞTIRMALIDIR: baseline oranı ile hedef oranı kıyaslanır."""
    baseline = _baseline()
    findings = detect_deviations(
        baseline,
        _baseline_observations() + _target_with_medium_shift(),
        T0 + timedelta(days=250),
        T0 + timedelta(days=400),
    )
    timeline = build_evidence_timeline(findings)

    by_signal = {entry.source_metrics["signal_id"]: entry for entry in timeline.entries}
    assert by_signal["ritual.obj.kitchen_table"].source_metrics["confounded_by_medium_change"] is True
    assert by_signal["habitat.is_daylight"].source_metrics["confounded_by_medium_change"] is True
    # Üretim biçiminin kendisi confound DEĞİLDİR: kendi eksenidir.
    assert by_signal[MEDIUM_SIGNAL].source_metrics["confounded_by_medium_change"] is False
    assert by_signal["ritual.obj.kitchen_table"].source_metrics["medium_change_status"] == "changed"


def test_target_only_input_cannot_claim_confound() -> None:
    """Baseline penceresi verilmezse karşılaştırma yapılamaz: sonuç ``unknown``.

    Ölçülemeyen durum "confound yok" sayılmaz; kayıt bunu taşır.
    """
    baseline = _baseline()
    findings = detect_deviations(
        baseline, _target_with_medium_shift(), T0 + timedelta(days=250), T0 + timedelta(days=400)
    )
    assert findings
    assert all(finding.confounded_by_medium_change is False for finding in findings)
    assert all(finding.medium_change_status == "unknown" for finding in findings)


def test_high_but_stable_authored_rate_is_not_confound() -> None:
    """Sözleşme #7: oran yüksek ama BASELINE'da da yüksek → confound değildir."""
    observations = (
        [_obs("timing.is_night_post", day, 0.0) for day in range(10)]
        + [_obs(MEDIUM_SIGNAL, day, 1.0) for day in range(10)]
        + [_obs("ritual.obj.kitchen_table", day, 1.0) for day in range(10)]
    )
    baseline = build_baseline(
        "s", observations, T0, T0 + timedelta(days=200), registry=default_registry(), strict=True
    )
    target = [
        _obs(MEDIUM_SIGNAL, 300 + 10 * i, 1.0) for i in range(6)
    ] + [_obs("ritual.obj.kitchen_table", 300, 0.0)]
    findings = detect_deviations(
        baseline, observations + target, T0 + timedelta(days=250), T0 + timedelta(days=400)
    )

    ritual = next(f for f in findings if f.signal_id == "ritual.obj.kitchen_table")
    assert ritual.medium_change_status == "stable"
    assert ritual.confounded_by_medium_change is False
    assert any(f.signal_id == MEDIUM_SIGNAL for f in findings) is False  # 1.0 → 1.0 sapma değil


def test_no_confound_when_medium_stays_incidental() -> None:
    baseline = _baseline()
    observations = _baseline_observations() + [
        _obs(MEDIUM_SIGNAL, 300, 0.0),
        _obs(MEDIUM_SIGNAL, 310, 0.0),
        _obs("ritual.obj.kitchen_table", 300, 0.0),
    ]
    findings = detect_deviations(
        baseline, observations, T0 + timedelta(days=250), T0 + timedelta(days=400)
    )
    assert all(finding.confounded_by_medium_change is False for finding in findings)


def test_medium_shift_rate_reports_none_when_unmeasured() -> None:
    assert medium_shift_rate([_obs("timing.post_hour", 1, 12.0)], T0, T0 + timedelta(days=10)) is None


# --- Sözleşme uyumu ---------------------------------------------------------


def test_entries_satisfy_evidence_models_contract() -> None:
    baseline = _baseline()
    target = [
        _obs("timing.is_night_post", 300, 1.0),
        _obs("ritual.obj.kitchen_table", 305, 0.0),
        _obs(MEDIUM_SIGNAL, 310, 1.0),
    ]
    timeline = build_evidence_timeline(
        detect_deviations(baseline, target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    )

    assert isinstance(timeline, EvidenceTimeline)
    assert timeline.entries
    for entry in timeline.entries:
        assert EVIDENCE_ID_RE.match(entry.evidence_id)
        assert entry.temporal_basis == "observed_at"
        assert entry.epistemic_type in ("observation", "absence", "inference")
        assert entry.source_engine == "life_rupture"
        assert entry.epistemic_note
        assert entry.content
        assert isinstance(entry.source_metrics, dict)


def test_timeline_is_chronological() -> None:
    baseline = _baseline()
    target = [
        _obs("ritual.obj.kitchen_table", 320, 0.0),
        _obs("timing.is_night_post", 300, 1.0),
        _obs("habitat.is_daylight", 310, 0.0),
    ]
    timeline = build_evidence_timeline(
        detect_deviations(baseline, target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    )
    stamps = [entry.timeline_at for entry in timeline.entries]
    assert stamps == sorted(stamps)


def test_unreliable_baseline_produces_no_finding() -> None:
    observations = [_obs("timing.is_night_post", day, 0.0) for day in range(3)]
    baseline = build_baseline("s", observations, T0, registry=default_registry())
    target = [_obs("timing.is_night_post", 300, 1.0)]
    assert detect_deviations(baseline, target, T0 + timedelta(days=250), T0 + timedelta(days=400)) == []
