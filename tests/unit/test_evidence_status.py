"""Kanıt durumunun UI'ya dürüst ve makine-okunur taşındığını kilitler."""

from agent_core.services.evidence_status import classify_evidence_status


def test_halted_evidence_has_explicit_turkish_label():
    result = classify_evidence_status(
        status="halted_evidence",
        halted_reason="profil gizli",
    )
    assert result["code"] == "insufficient_evidence"
    assert result["label"] == "YETERSİZ KANIT"
    assert result["decision_grade"] is False


def test_completed_no_decision_is_not_presented_as_evidence():
    result = classify_evidence_status(
        status="completed",
        runs={
            "resonance_calc": {
                "status": "completed_no_decision",
                "decision_grade": False,
                "output_summary": {"data_confidence": False},
            }
        },
        evidence_chain=[{"agent": "resonance_calc"}],
    )
    assert result["code"] == "insufficient_evidence"
    assert result["label"] == "YETERSİZ KANIT"


def test_decision_grade_run_is_not_marked_insufficient():
    result = classify_evidence_status(
        status="completed",
        runs={
            "mirror_truth": {
                "status": "completed",
                "decision_grade": True,
                "output_summary": {"data_confidence": True},
            }
        },
        evidence_chain=[{"agent": "mirror_truth"}],
    )
    assert result["code"] == "available"
    assert result["decision_grade"] is True
