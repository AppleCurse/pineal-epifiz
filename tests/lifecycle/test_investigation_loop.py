from datetime import datetime, timezone
import pytest

from agent_core.domain.evidence_models import EvidenceTimeline, EvidenceTimelineEntry
from agent_core.investigation.loop import (
    HypothesisStatus,
    InquestHypothesis,
    InquestVerdict,
    InvestigationLoop,
    InvestigationRound,
    LeadInquirer,
    MicroTask,
    MicroTaskCoordinate,
    make_hypothesis_id,
    make_task_id,
)
from agent_core.lifecycle.baseline_builder import (
    BaselineProfile,
    SignalBaseline,
    SignalObservation,
)
from agent_core.lifecycle.deviation_detector import (
    DeviationDetector,
)
from agent_core.lifecycle.rupture_engine import RuptureEngine


def _make_sample_baseline(subject_id: str = "subj_001") -> BaselineProfile:
    b1 = SignalBaseline(
        signal_id="night_share",
        mean=0.10,
        std=0.02,
        sample_count=20,
    )
    b2 = SignalBaseline(
        signal_id="post_frequency_per_day",
        mean=1.5,
        std=0.2,
        sample_count=20,
    )
    b3 = SignalBaseline(
        signal_id="staged_media_ratio",
        mean=0.20,
        std=0.05,
        sample_count=20,
    )
    return BaselineProfile(
        subject_id=subject_id,
        window_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        baselines={"night_share": b1, "post_frequency_per_day": b2, "staged_media_ratio": b3},
        correlation_verified=True,
    )


def test_helper_id_generators():
    hid = make_hypothesis_id("What is the relation?")
    assert hid.startswith("hyp_")
    tid = make_task_id(hid, "targeted_drill", "vision")
    assert tid.startswith("mt_")


def test_multi_round_inquest_confirmed():
    subject_id = "subj_001"
    base_time = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    baseline = _make_sample_baseline(subject_id)

    def dispatcher(round_type: InvestigationRound, tasks: list[MicroTask]) -> list[SignalObservation]:
        if round_type == InvestigationRound.BROAD_RECON:
            # Round 1: Returns initial broad signals (significant deviation)
            return [
                SignalObservation(
                    signal_id="night_share",
                    timestamp=base_time,
                    value=0.85,
                    source_ref="recon_batch_1",
                ),
                SignalObservation(
                    signal_id="post_frequency_per_day",
                    timestamp=base_time,
                    value=0.0,
                    source_ref="recon_batch_1",
                    measurement_status="absence",
                ),
            ]
        elif round_type == InvestigationRound.TARGETED_DRILL:
            # Round 2: Targeted drill confirms supporting evidence
            return [
                SignalObservation(
                    signal_id="night_share",
                    timestamp=datetime(2026, 3, 5, 2, 0, tzinfo=timezone.utc),
                    value=0.90,
                    source_ref="drill_batch_2",
                )
            ]
        elif round_type == InvestigationRound.FALSIFICATION:
            # Round 3: Falsification check finds NO counter-evidence
            return [
                SignalObservation(
                    signal_id="night_share",
                    timestamp=datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc),
                    value=0.88,
                    source_ref="falsify_batch_3",
                )
            ]
        return []

    loop = InvestigationLoop(
        max_rounds=3,
        detector=DeviationDetector(baseline),
        rupture_engine=RuptureEngine(baseline),
    )
    report = loop.run_inquest(
        subject_id=subject_id,
        dispatcher=dispatcher,
        baseline_profile=baseline,
        target_start=base_time,
        target_end=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert report.total_rounds == 3
    assert report.verdict == InquestVerdict.CONFIRMED
    assert not report.circuit_breaker_triggered
    assert len(report.round_history) == 3


def test_rule_1_no_agent_runs_blind_without_coordinates():
    class BrokenInquirer(LeadInquirer):
        def generate_targeted_tasks(self, hypotheses, round_type):
            tasks = super().generate_targeted_tasks(hypotheses, round_type)
            if tasks:
                tasks[0].coordinate = MicroTaskCoordinate()
            return tasks

    loop = InvestigationLoop(inquirer=BrokenInquirer(), max_rounds=2)
    with pytest.raises(ValueError, match="Kural 1 ihlali"):
        loop.run_inquest(
            subject_id="subj_001",
            dispatcher=lambda r, t: [
                SignalObservation(
                    signal_id="test",
                    timestamp=datetime.now(timezone.utc),
                    value=1.0,
                )
            ] if r == InvestigationRound.BROAD_RECON else [],
        )


def test_rule_2_unresolved_hypotheses_become_unverified():
    inquirer = LeadInquirer()
    hyp = InquestHypothesis(
        hypothesis_id="hyp_open",
        question="Unanswered question?",
        signal_type="unknown_signal",
        formulated_in_round=1,
        status=HypothesisStatus.OPEN,
    )
    timeline = EvidenceTimeline()
    report = inquirer.seal_verdict(
        subject_id="subj_001",
        total_rounds=2,
        hypotheses=[hyp],
        timeline=timeline,
        rupture_report=None,
        circuit_breaker=False,
        round_history=[],
    )
    assert hyp.status == HypothesisStatus.UNVERIFIED
    assert "Unanswered question?" in report.unresolved_questions
    assert report.verdict == InquestVerdict.INSUFFICIENT_EVIDENCE


def test_rule_3_circuit_breaker_halts_on_zero_evidence():
    subject_id = "subj_001"
    base_time = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

    def dispatcher(round_type: InvestigationRound, tasks: list[MicroTask]) -> list[SignalObservation]:
        if round_type == InvestigationRound.BROAD_RECON:
            return [
                SignalObservation(
                    signal_id="night_share",
                    timestamp=base_time,
                    value=0.9,
                )
            ]
        # Round 2 yields 0 evidence
        return []

    loop = InvestigationLoop(max_rounds=3)
    report = loop.run_inquest(
        subject_id=subject_id,
        dispatcher=dispatcher,
    )

    assert report.circuit_breaker_triggered
    assert report.total_rounds == 2  # Broke early in round 2
    assert report.verdict == InquestVerdict.INSUFFICIENT_EVIDENCE


def test_falsification_counter_evidence_triggers_falsified_verdict():
    subject_id = "subj_001"
    base_time = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

    def dispatcher(round_type: InvestigationRound, tasks: list[MicroTask]) -> list[SignalObservation]:
        if round_type == InvestigationRound.BROAD_RECON:
            return [
                SignalObservation(
                    signal_id="night_share",
                    timestamp=base_time,
                    value=0.9,
                )
            ]
        elif round_type == InvestigationRound.TARGETED_DRILL:
            return [
                SignalObservation(
                    signal_id="night_share",
                    timestamp=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
                    value=0.9,
                )
            ]
        elif round_type == InvestigationRound.FALSIFICATION:
            # Round 3 finds counter-evidence!
            return [
                SignalObservation(
                    signal_id="night_share",
                    timestamp=datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
                    value=0.1,
                    source_ref="counter_evidence",
                )
            ]
        return []

    loop = InvestigationLoop(max_rounds=3)
    report = loop.run_inquest(subject_id=subject_id, dispatcher=dispatcher)

    assert report.verdict == InquestVerdict.FALSIFIED
    assert any(h.status == HypothesisStatus.FALSIFIED for h in report.hypotheses)


def test_direct_inquirer_methods():
    inquirer = LeadInquirer()
    assert inquirer.circuit_breaker_check(0) is True
    assert inquirer.circuit_breaker_check(5) is False

    # Direct test of evaluate_round
    hyp = InquestHypothesis(
        hypothesis_id="hyp_direct",
        question="Direct test question?",
        signal_type="test_signal",
        formulated_in_round=1,
    )
    entry = EvidenceTimelineEntry(
        evidence_id="ev_01234567890123456789",
        timeline_at=datetime.now(timezone.utc),
        temporal_basis="observed_at",
        epistemic_type="observation",
        epistemic_note="direct test",
        source_engine="test_engine",
        content="direct test content",
        source_metrics={"signal_id": "test_signal", "is_counter_evidence": True},
    )
    inquirer.evaluate_round(2, [hyp], [entry], is_falsification_round=True)
    assert hyp.status == HypothesisStatus.FALSIFIED
