"""Mutabakat etiketi ritüel eksenini AÇAR — ama ölçüm gibi görünmeden.

Kilitlenen iddialar:
    * ``corroborated_objects`` sözlüğü besler; ``ritual.obj.*`` sinyali doğar,
    * bu sinyallerin kanıt derecesi ``corroborated``dır (``measured`` değil) ve
      raporda AYRI sayılır + ``unknowns``ta yazılıdır,
    * araç ölçümü (``detected_objects``) varsa derece ``measured`` olur,
    * mutabakat yoksa ritüel ekseni KAPALI kalır (tek model iddiası yetmez),
    * ölen ritüel 0.0 olarak ölçülür (yokluk kaydedilir, kayıtsızlık değil).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_core.lifecycle.observation_adapter import ObservationAdapter
from agent_core.lifecycle.pipeline import analyze_life_rupture

BASE = datetime(2021, 1, 4, 12, tzinfo=timezone.utc)
#: 40 hafta ≈ 280 gün: baseline ilk 180 günü alır, geri kalanı KARŞILAŞTIRMA
#: penceresidir. 26 hafta olsaydı hedef pencere boş kalır ve hiçbir eksen
#: ölçülemezdi (uydurma yerine "ölçülemedi").
WEEKS = 40
#: Mutabakat etiketi baseline penceresinin TAMAMINDA var (26 hafta), sonra yok:
#: sabit baseline (1.0) kırılır → ``constant_break``. Etiket 20. haftada ölseydi
#: baseline 0.77 merkezli olur ve z=1.79 eşiği aşmadığı için sapma görünmezdi.
RITUAL_UNTIL = 26


def _profile() -> dict:
    """Haftalık gönderi serisi: 26 hafta, tarihli."""
    return {
        "posts": ["kelime " * (6 + index % 5) for index in range(WEEKS)],
        "post_times": [(BASE + timedelta(days=7 * index)).isoformat() for index in range(WEEKS)],
    }


def _frame(
    index: int,
    *,
    corroborated: list[str] | None = None,
    measured: list[str] | None = None,
    places: list[str] | None = None,
) -> dict:
    return {
        "frame_id": f"fr_{index:04d}",
        "observed_at": (BASE + timedelta(days=7 * index)).isoformat(),
        "capture_class": "unknown",
        "has_measurable_background": True,
        "detected_objects": list(measured or []),
        "environment_and_places": [],
        "corroborated_objects": list(corroborated or []),
        "corroborated_places": list(places or []),
        "corroboration_counts": {label: 2 for label in (corroborated or [])},
        "lighting": "unknown",
        "visual_stats": {
            "brightness": 0.3 + 0.01 * (index % 7),
            "saturation": 0.4,
            "contrast": 0.5,
            "edge_density": 0.2,
            "colorfulness": 0.3,
        },
        "data_confidence": True,
    }


def _dying_ritual_frames() -> list[dict]:
    """Mutabakat etiketi ilk yarıda VAR, ikinci yarıda YOK → ölen ritüel."""
    return [
        _frame(index, corroborated=["kitchen table"] if index < RITUAL_UNTIL else [])
        for index in range(WEEKS)
    ]


def _report(frames: list[dict]):
    return analyze_life_rupture(_profile(), visual_evidence={"frames": frames})


def test_corroborated_labels_open_the_ritual_axis() -> None:
    report = _report(_dying_ritual_frames())

    axis = next(axis for axis in report.axes if axis.axis == "ritual")
    assert axis.state == "measured"
    assert axis.baseline_signal_count >= 1
    # Ritüelin ölümü SAPMA olarak görünür (yokluk kaydedilir).
    assert "ritual.obj.kitchen_table" in axis.deviating_signals
    finding = next(f for f in report.findings if f.signal_id == "ritual.obj.kitchen_table")
    assert finding.direction in ("disappeared", "decreased")
    assert finding.baseline_value is not None and finding.baseline_value > 0.5
    assert finding.observed_value == 0.0


def test_dying_ritual_is_measured_as_zero_not_as_missing() -> None:
    observations = ObservationAdapter().transform(
        None, visual_evidence={"frames": _dying_ritual_frames()}
    )
    ritual = [
        observation
        for observation in observations
        if observation.signal_id == "ritual.obj.kitchen_table"
    ]

    assert ritual
    values = [observation.value for observation in ritual]
    assert 1.0 in values and 0.0 in values  # varlık → yokluk, eksik gözlem değil


def test_corroborated_signals_are_counted_separately() -> None:
    report = _report(_dying_ritual_frames())

    assert report.evidence_grade_counts.get("corroborated", 0) > 0
    assert report.corroborated_signal_count == report.evidence_grade_counts["corroborated"]
    assert report.evidence_grade_counts.get("measured", 0) > 0
    assert any("kanıt dereceleri" in unknown for unknown in report.unknowns)
    assert "araç ölçümü değil" in " ".join(report.unknowns)


def test_measured_labels_keep_their_grade() -> None:
    frames = [_frame(index, measured=["kitchen table"]) for index in range(WEEKS)]
    observations = ObservationAdapter().transform(None, visual_evidence={"frames": frames})
    ritual = [
        observation
        for observation in observations
        if observation.signal_id == "ritual.obj.kitchen_table"
    ]

    assert ritual
    assert {observation.context.get("evidence_grade") for observation in ritual} == {"measured"}


def test_without_consensus_the_ritual_axis_stays_closed() -> None:
    """Tek model iddiası yetmez: ``corroborated_objects`` boşsa eksen açılmaz."""
    frames = [_frame(index) for index in range(WEEKS)]
    report = _report(frames)

    assert not [row for row in report.data_coverage if row["signal_id"].startswith("ritual.")]
    assert report.corroborated_signal_count == 0
    assert report.corroborated_labels == []
    axis = next(axis for axis in report.axes if axis.axis == "ritual")
    assert axis.state == "suppressed"


def test_corroborated_labels_are_reported_with_grade_and_agreement() -> None:
    report = _report(_dying_ritual_frames())

    assert report.corroborated_labels
    for row in report.corroborated_labels:
        assert row["observation_grade"] == "corroborated"
        assert row["agreement_count"] >= 2


def test_report_identity_tracks_corroborated_evidence() -> None:
    with_labels = _report(_dying_ritual_frames())
    without_labels = _report([_frame(index) for index in range(WEEKS)])

    assert with_labels.report_id != without_labels.report_id
    assert _report(_dying_ritual_frames()).report_id == with_labels.report_id


def test_ritual_vocabulary_is_discovered_not_listed() -> None:
    """Sözlük veriden çıkar: etiket değişirse sinyal adı da değişir, kod aynı kalır."""
    other = [_frame(index, measured=["wooden crate"] if index < RITUAL_UNTIL else []) for index in range(WEEKS)]
    report = _report(other)

    ritual_signals = [
        row["signal_id"] for row in report.data_coverage if row["signal_id"].startswith("ritual.")
    ]
    assert "ritual.obj.wooden_crate" in ritual_signals
    assert not [signal for signal in ritual_signals if "kitchen" in signal]
