"""Strata köprüsü — gerçek ``StrataReport`` alan adlarını (``fossils`` / ``drifts``) kilitler."""

from __future__ import annotations

from agent_core.domain.pillar_models import EvidenceStatus
from agent_core.domain.pillar_wave2_models import FossilRecord, IdentityDrift, StrataReport
from agent_core.lifecycle.strata_bridge import extract_strata_drifts


def _report() -> dict:
    return StrataReport(
        status=EvidenceStatus.OBSERVED,
        fossils=[
            FossilRecord(
                topic="Home Living Room",
                last_seen_iso="2022-06-15T00:00:00+00:00",
                extinction_confidence=0.92,
                early_presence=0.8,
                late_presence=0.05,
                evidence_refs=["post:1"],
            )
        ],
        drifts=[
            IdentityDrift(
                metric="solitude ratio",
                early_value=0.2,
                late_value=0.85,
                drift_ratio=3.25,
                is_significant=True,
            )
        ],
    ).model_dump(mode="json")


def test_real_strata_report_fields_are_read() -> None:
    drifts, problems = extract_strata_drifts(_report())

    assert problems == []
    assert {drift.signal_id for drift in drifts} == {
        "strata.fossil.home_living_room",
        "strata.drift.solitude_ratio",
    }

    fossil = next(drift for drift in drifts if drift.is_fossil)
    assert fossil.is_significant is True
    assert fossil.last_seen is not None and fossil.last_seen.year == 2022
    assert fossil.evidence_refs == ("post:1",)

    drift = next(item for item in drifts if not item.is_fossil)
    assert drift.last_seen is None  # drift kaydı tarih taşımaz → undated
    assert drift.is_significant is True


def test_weak_extinction_is_not_significant() -> None:
    payload = _report()
    payload["fossils"][0]["extinction_confidence"] = 0.4
    drifts, _ = extract_strata_drifts(payload)
    assert drifts[0].is_significant is False


def test_missing_or_malformed_map_fails_closed() -> None:
    assert extract_strata_drifts(None) == ([], [])
    drifts, problems = extract_strata_drifts({"fossils": ["bozuk"], "drifts": [{"metric": ""}]})
    assert drifts == []
    assert any("invalid_fossil" in problem for problem in problems)
    assert any("drift_without_metric" in problem for problem in problems)
