from datetime import datetime, timezone

import pytest

from agent_core.agents.autonomous_verifier import AutonomousVerifier
from agent_core.domain.pillar_models import EvidenceStatus, SeismicEvent, SeismicKind, SeismosReport
from agent_core.domain.pillar_wave2_models import FullPillarBundle
from agent_core.services.pillar_evidence_adapter import adapt_pillar_bundle


T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)


class NoExternalSearch:
    tavily_key = "configured-but-must-not-be-used-for-canonical-checks"
    serpapi_key = None
    exa_key = None

    def __init__(self):
        self.calls = []

    async def search(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("canonical observations must not use external search")


def _bundle():
    event = SeismicEvent(
        event_id="sez_dual_mode_1",
        kind=SeismicKind.SILENCE_GAP,
        intensity=4.0,
        timestamp=T0,
        window_start=T0,
        window_end=T0,
        observables=["A posting gap was measured between two dated posts."],
        metrics={"gap_hours": 48.0},
        hypotheses=["Cause unknown."],
        status=EvidenceStatus.OBSERVED,
        evidence_refs=["post:2025-01-01T00:00:00+00:00", "post:2025-01-03T00:00:00+00:00"],
    )
    return FullPillarBundle(
        seismos=SeismosReport(status=EvidenceStatus.OBSERVED, events=[event])
    )


@pytest.mark.asyncio
async def test_internal_observation_checks_run_without_bio_or_external_search():
    bundle = _bundle()
    target_profile = {"bio": "", "posts": []}
    items = adapt_pillar_bundle(bundle, target_profile=target_profile)
    observations = [item for item in items if item.epistemic_type == "observation"]
    assert observations

    search = NoExternalSearch()
    verifier = AutonomousVerifier(search_engine=search)
    report = await verifier.execute(
        {
            "target_profile": target_profile,
            "pillar_bundle": bundle.model_dump(mode="json"),
            "forensic_evidence": [item.model_dump(mode="json") for item in items],
        },
        memory=None,
        llm_gateway=None,
    )

    assert report.status == "UNVERIFIED"
    assert report.fallback_reason == "no_bio"
    assert search.calls == []
    assert len(report.canonical_observation_checks) == len(observations)
    assert all(item.factual_truth_status == "BİLİNMİYOR" for item in report.canonical_observation_checks)
    assert all(item.factual_verdict_issued is False for item in report.canonical_observation_checks)
    assert all(item.downstream_decision_state == "NO_FACTUAL_VERDICT" for item in report.canonical_observation_checks)
    assert all(item.provenance_integrity == "valid" for item in report.canonical_observation_checks)
    assert all(item.source_consistency == "consistent" for item in report.canonical_observation_checks)
    assert all(item.reproducibility == "reproduced" for item in report.canonical_observation_checks)


def test_canonical_integrity_mismatch_is_not_a_factual_yalan_verdict():
    bundle = _bundle()
    target_profile = {"bio": "", "posts": []}
    items = adapt_pillar_bundle(bundle, target_profile=target_profile)
    observation = next(item for item in items if item.epistemic_type == "observation")
    tampered = observation.model_copy(update={"content": "Changed after canonicalization."})

    checks, rejected = AutonomousVerifier._check_canonical_observations({
        "target_profile": target_profile,
        "pillar_bundle": bundle.model_dump(mode="json"),
        "forensic_evidence": [tampered.model_dump(mode="json")],
    })

    assert rejected == 0
    assert len(checks) == 1
    assert checks[0].source_consistency == "mismatch"
    assert checks[0].reproducibility == "mismatch"
    assert checks[0].factual_truth_status == "BİLİNMİYOR"
    assert checks[0].factual_verdict_issued is False


def test_without_source_bundle_provenance_is_reported_unverified_not_invalid():
    bundle = _bundle()
    target_profile = {"bio": "", "posts": []}
    observation = next(
        item for item in adapt_pillar_bundle(bundle, target_profile=target_profile)
        if item.epistemic_type == "observation"
    )

    checks, rejected = AutonomousVerifier._check_canonical_observations({
        "target_profile": target_profile,
        "forensic_evidence": [observation.model_dump(mode="json")],
    })

    assert rejected == 0
    assert checks[0].provenance_integrity == "present_unverified"
    assert checks[0].source_consistency == "not_checked"
    assert checks[0].reproducibility == "not_checked"
    assert checks[0].factual_truth_status == "BİLİNMİYOR"


def test_malformed_canonical_record_is_counted_but_not_given_a_verdict():
    checks, rejected = AutonomousVerifier._check_canonical_observations({
        "forensic_evidence": [{"epistemic_type": "observation", "content": "missing required fields"}]
    })

    assert checks == []
    assert rejected == 1
