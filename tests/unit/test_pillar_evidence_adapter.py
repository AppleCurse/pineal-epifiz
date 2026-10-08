from datetime import datetime, timezone

from pydantic import ValidationError
import pytest

from agent_core.domain.evidence_models import EvidenceItem
from agent_core.domain.pillar_models import (
    AbsenceHypothesis,
    EvidenceStatus,
    FlowWindow,
    FrequencyReport,
    PhaseShift,
    SeismicEvent,
    SeismicKind,
    SeismosReport,
    VoidReport,
    VoidSignal,
    WaveSample,
)
from agent_core.domain.pillar_wave2_models import (
    BiometricSignal,
    FullPillarBundle,
    FossilRecord,
    GravityReport,
    GravityWell,
    IdentityDrift,
    KeyReport,
    PulseReport,
    StrataReport,
)
from agent_core.services.pillar_evidence_adapter import adapt_pillar_bundle


T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
T1 = datetime(2024, 3, 1, tzinfo=timezone.utc)


def _bundle() -> FullPillarBundle:
    event = SeismicEvent(
        event_id="sez_test_1",
        kind=SeismicKind.SILENCE_GAP,
        intensity=8.0,
        timestamp=T0,
        window_start=T0,
        window_end=T1,
        observables=["47 saatlik paylaşım boşluğu."],
        metrics={"gap_hours": 47.0, "ratio": 4.2},
        hypotheses=["Travel or missing data could explain the gap."],
        status=EvidenceStatus.OBSERVED,
        evidence_refs=["post:2024-01-01T00:00:00+00:00", "post:2024-03-01T00:00:00+00:00"],
    )
    void_signal = VoidSignal(
        topic="family",
        category="family",
        expected_presence=0.22,
        actual_presence=0.03,
        absence_delta=0.19,
        absence_score=0.86,
        status=EvidenceStatus.WEAK,
        hypotheses=[AbsenceHypothesis.SUPPRESSION, AbsenceHypothesis.UNKNOWN],
        observables=["Kategori 'family': beklenen≈0.22, gözlenen≈0.03.", "Cue hit=1."],
        evidence_refs=["void:family:hits=1"],
    )
    return FullPillarBundle(
        frequency=FrequencyReport(
            status=EvidenceStatus.OBSERVED,
            samples=[
                WaveSample(
                    t=T0,
                    energy=0.8,
                    post_count=2,
                    mean_text_len=40,
                    engagement=3,
                    platform="example",
                )
            ],
            flow_windows=[
                FlowWindow(
                    start=T0,
                    end=T1,
                    peak_energy=0.8,
                    mean_energy=0.6,
                    sample_count=2,
                    label="flow",
                )
            ],
            phase_shifts=[
                PhaseShift(platform_a="example", platform_b="other", lag_hours=2.0, correlation=0.75)
            ],
            energy_mean=0.5,
            energy_std=0.2,
            night_energy_share=0.6,
            evidence_refs=["frequency:2"],
        ),
        seismos=SeismosReport(status=EvidenceStatus.OBSERVED, events=[event]),
        void=VoidReport(
            status=EvidenceStatus.WEAK,
            signals=[void_signal],
            top_voids=["family"],
            covered_categories=["family", "career"],
            evidence_refs=["corpus_tokens:84"],
        ),
        strata=StrataReport(
            status=EvidenceStatus.OBSERVED,
            fossils=[
                FossilRecord(
                    topic="music",
                    last_seen_iso="2024-01-15T00:00:00+00:00",
                    extinction_confidence=0.75,
                    early_presence=0.6,
                    late_presence=0.01,
                    observables=["'music' early active, late not observed."],
                    evidence_refs=["fossil:music"],
                )
            ],
            drifts=[
                IdentityDrift(
                    metric="text_length",
                    early_value=120.0,
                    late_value=75.0,
                    drift_ratio=0.625,
                    is_significant=True,
                    observable="text_length: 120.000→75.000.",
                )
            ],
            early_range="2024-01-01→2024-01-31",
            late_range="2024-02-01→2024-03-01",
            evidence_refs=["strata:depth_days=60"],
        ),
        gravity=GravityReport(
            status=EvidenceStatus.OBSERVED,
            wells=[
                GravityWell(
                    anchor="music",
                    mass=2.0,
                    density=0.5,
                    pull=1.25,
                    recurrence=3,
                    is_black_hole=True,
                    observables=["Anchor 'music' recurred three times."],
                    evidence_refs=["gravity:music"],
                )
            ],
            total_anchors_scanned=5,
        ),
        pulse=PulseReport(
            status=EvidenceStatus.OBSERVED,
            signals=[
                BiometricSignal(
                    signal_type="text_length",
                    label="Text length",
                    value=40,
                    z_score=1.5,
                    baseline=25,
                    interpretation="above engine threshold",
                )
            ],
            baseline_volatility=0.2,
            rhythm_signature="steady",
            evidence_refs=["pulse:text_length"],
        ),
        key=KeyReport(
            status=EvidenceStatus.WEAK,
            frequency_signature="Night-weighted label from frequency metrics.",
            core_tension="Possible cross-pillar tension; not a direct observation.",
            rhythm_note="Rule-derived non-biological rhythm label.",
            gate_key="Open a low-pressure conversation about a recurring topic.",
            walls=[
                "Avoid assuming a past topic is a personal boundary.",
                "Do not infer a personal boundary from corpus gaps.",
            ],
            timing_window="Daytime heuristic.",
            confidence=0.5,
            evidence_refs=["key:synthesized"],
        ),
    )


def _by_content(items, text):
    return next(item for item in items if item.content == text)


def test_frequency_gravity_and_pulse_keep_source_metrics_uninterpreted():
    items = adapt_pillar_bundle(_bundle())
    frequency = next(
        item for item in items
        if item.source_engine == "frequency_engine" and item.source_metrics.get("energy_mean") == 0.5
    )
    gravity = next(item for item in items if item.source_engine == "gravity_engine")
    pulse = next(item for item in items if item.source_engine == "pulse_engine")
    phase = next(
        item for item in items
        if item.source_engine == "frequency_engine" and item.source_metrics.get("lag_hours") == 2.0
    )
    sample = next(
        item for item in items
        if item.source_engine == "frequency_engine" and item.source_metrics.get("energy") == 0.8
    )

    assert frequency.source_metrics["night_energy_share"] == 0.6
    assert phase.source_metrics["correlation"] == 0.75
    assert sample.observed_at == T0
    assert "bucket timestamp" in sample.scope["timestamp_semantics"]
    assert gravity.source_metrics["recurrence"] == 3
    assert "not stated preference" in gravity.scope["measurement"]
    assert pulse.source_metrics["source_baseline"] == 25
    assert pulse.scope["measurement_domain"] == "textual posts only"
    assert all(item.confidence is None for item in (frequency, phase, gravity, pulse))


def test_seismos_observation_and_hypothesis_are_separate_types():
    items = adapt_pillar_bundle(_bundle())

    observation = _by_content(items, "47 saatlik paylaşım boşluğu.")
    hypothesis = _by_content(items, "Travel or missing data could explain the gap.")

    assert observation.epistemic_type == "observation"
    assert observation.observed_at == T0
    assert observation.window_start == T0
    assert observation.window_end == T1
    assert observation.scope["source_count"] is None
    assert observation.scope["time_window"] is None
    assert observation.source_metrics["intensity"] == 8.0
    assert observation.source_metrics["gap_hours"] == 47.0
    assert observation.confidence is None
    assert hypothesis.epistemic_type == "inference"
    assert hypothesis.scope["interpretation"].startswith("engine-generated")
    assert hypothesis.confidence is None


def test_void_is_corpus_scoped_and_not_personal_baseline():
    profile = {
        "platform": "example",
        "bio": "A short public bio.",
        "posts": [
            {"text": "One public post.", "created_at": "2024-01-01T00:00:00Z"},
            "Another public post.",
        ],
    }
    items = adapt_pillar_bundle(_bundle(), target_profile=profile)
    absence = _by_content(
        items,
        "Kategori 'family': beklenen≈0.22, gözlenen≈0.03. Cue hit=1.",
    )

    assert absence.epistemic_type == "absence"
    assert absence.scope["corpus_basis"] == "target_profile.bio + target_profile.posts"
    assert absence.scope["interest_metadata_available"] is False
    assert absence.scope["source_count"] == 3
    assert absence.scope["time_window"]["start"].startswith("2024-01-01")
    assert "not a personal historical baseline" in absence.scope["comparison_basis"]
    assert absence.source_metrics["absence_score"] == 0.86
    assert absence.confidence is None

    hypotheses = [item for item in items if item.source_engine == "void_engine" and item.epistemic_type == "inference"]
    assert len(hypotheses) == 2
    assert all("does not establish motive" in item.scope["interpretation"] for item in hypotheses)


def test_void_scope_discloses_interest_metadata_used_for_prior_adjustment():
    items = adapt_pillar_bundle(
        _bundle(),
        target_profile={"interests": ["family"]},
    )
    absence = next(item for item in items if item.epistemic_type == "absence")

    assert absence.scope["interest_metadata_available"] is True
    assert "optionally boosted" in absence.scope["comparison_basis"]
    assert "not a personal historical baseline" in absence.scope["comparison_basis"]


def test_strata_drift_and_fossil_keep_their_scope_and_source_scores():
    items = adapt_pillar_bundle(_bundle())
    drift = _by_content(items, "text_length: 120.000→75.000.")
    fossil = _by_content(items, "'music' early active, late not observed.")

    assert drift.epistemic_type == "observation"
    assert drift.source_metrics["is_significant_threshold_flag"] is True
    assert "not a statistical p-value" in drift.scope["significance_note"]
    assert fossil.epistemic_type == "absence"
    assert fossil.scope["absence_scope"] == "late subset only"
    assert fossil.source_metrics["source_extinction_confidence"] == 0.75
    assert fossil.confidence is None


def test_key_advice_is_strategy_and_report_score_is_not_confidence():
    items = adapt_pillar_bundle(_bundle())
    gate = _by_content(items, "Open a low-pressure conversation about a recurring topic.")
    wall = _by_content(items, "Avoid assuming a past topic is a personal boundary.")
    frequency_label = _by_content(items, "Night-weighted label from frequency metrics.")
    rhythm_label = _by_content(items, "Rule-derived non-biological rhythm label.")

    assert frequency_label.epistemic_type == "inference"
    assert rhythm_label.epistemic_type == "inference"
    assert gate.epistemic_type == "strategy"
    assert wall.epistemic_type == "strategy"
    assert wall.scope["not_an_established_personal_boundary"] is True
    assert gate.confidence is None
    assert gate.source_metrics["source_key_report_confidence"] == 0.5
    assert "not calibrated probability" in gate.scope["reported_confidence_semantics"]


def test_adapter_is_deterministic_across_model_and_json_inputs():
    bundle = _bundle()
    profile = {"platform": "example", "bio": "bio", "posts": ["post"]}

    first = adapt_pillar_bundle(bundle, target_profile=profile)
    second = adapt_pillar_bundle(bundle.model_dump(mode="json"), target_profile=profile)
    reordered = bundle.model_copy(
        update={
            "computed_at": T1,
            "key": bundle.key.model_copy(update={"walls": list(reversed(bundle.key.walls))}),
        }
    )
    third = adapt_pillar_bundle(reordered, target_profile=profile)

    expected = [item.model_dump(mode="json") for item in first]
    assert expected == [item.model_dump(mode="json") for item in second]
    assert expected == [item.model_dump(mode="json") for item in third]
    assert len({item.evidence_id for item in first}) == len(first)
    for item in first:
        restored = EvidenceItem.model_validate_json(item.model_dump_json())
        assert restored == item
        assert item.confidence is None


def test_empty_bundle_produces_no_synthetic_evidence():
    assert adapt_pillar_bundle(None) == []
    assert adapt_pillar_bundle(FullPillarBundle()) == []
    assert adapt_pillar_bundle(
        FullPillarBundle(frequency=FrequencyReport(status=EvidenceStatus.OBSERVED))
    ) == []


def test_evidence_item_is_strict_and_confidence_is_bounded():
    data = {
        "evidence_id": "ev_0123456789abcdefabcd",
        "epistemic_type": "observation",
        "source_engine": "seismos_engine",
        "source_status": EvidenceStatus.OBSERVED,
        "content": "Observed post gap.",
        "confidence": None,
        "unknown": "not allowed",
    }
    with pytest.raises(ValidationError):
        EvidenceItem(**data)

    data.pop("unknown")
    data["confidence"] = 1.1
    with pytest.raises(ValidationError):
        EvidenceItem(**data)
