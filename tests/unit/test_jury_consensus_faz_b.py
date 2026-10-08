"""FAZ B · B1 — BAĞIMSIZ JÜRİ KONSENSÜS DENETÇİSİ sözleşme testleri.

Kilitlenen iddialar:
1. Panelin oyları İKİNCİ ve BAĞIMSIZ bir yerde yeniden sayılır; panel kendi
   aritmetiğine güvenmez (duh fikri: aynı hipotezi ikinci kafaya okutmak).
2. Yeter sayı (quorum) altındaki hüküm konsensüs SAYILMAZ ve işaretlenir.
3. Uyuşmazlık GİZLENMEZ: rapora yazılır, karar kuralında görünür.
4. Bağlayıcı kipte (`PINEAL_JURY_BINDING=true`) uyuşmazlıkta denetçinin
   bulduğu hüküm geçerli olur ve iddia DÜŞÜRÜLÜR (sayılar yeniden hesaplanır).
5. Denetçi LLM çağırmaz, ağa çıkmaz: deterministiktir.
"""

from __future__ import annotations

import pytest

from agent_core.services.jury_consensus import (
    VOTE_CONTRADICTED,
    VOTE_FALSE,
    VOTE_UNKNOWN,
    VOTE_VERIFIED,
    audit_claim,
    binding_enabled,
    consensus_downgrades,
    quorum,
    summarize,
)


class _FakeResult:
    def __init__(self, votes, verdict, claim_id="clm_1", text="deneme iddiası"):
        self.juror_votes = votes
        self.truth_status = verdict
        self.claim_id = claim_id
        self.claim_text = text


# -------------------------------------------------- 1 · bağımsız yeniden sayım
def test_audit_recomputes_tally_and_agrees_on_clean_majority():
    result = _FakeResult(
        {"a": VOTE_VERIFIED, "b": VOTE_VERIFIED, "c": VOTE_FALSE}, VOTE_VERIFIED
    )
    audit = audit_claim(result)
    assert audit.seats == 3
    assert audit.counted == 3
    assert audit.tally == {VOTE_VERIFIED: 2, VOTE_FALSE: 1}
    assert audit.recomputed_verdict == VOTE_VERIFIED
    assert audit.agreement is True
    assert audit.dissent == ["c"]
    assert audit.consensus_strength == pytest.approx(2 / 3, abs=1e-4)


def test_audit_catches_a_wrong_majority_claim():
    """Panel çoğunluk YOKKEN hüküm ilan ettiyse denetçi yakalar."""
    result = _FakeResult(
        {"a": VOTE_VERIFIED, "b": VOTE_FALSE, "c": VOTE_CONTRADICTED}, VOTE_VERIFIED
    )
    audit = audit_claim(result)
    assert audit.recomputed_verdict == VOTE_UNKNOWN  # berabere
    assert audit.agreement is False
    assert any("berabere" in note for note in audit.notes)


def test_audit_catches_verdict_that_no_seat_cast():
    result = _FakeResult({"a": VOTE_UNKNOWN, "b": VOTE_UNKNOWN}, VOTE_VERIFIED)
    audit = audit_claim(result)
    assert audit.counted == 0
    assert audit.recomputed_verdict == VOTE_UNKNOWN
    assert audit.agreement is False


def test_no_votes_is_unknown_not_a_verdict():
    audit = audit_claim(_FakeResult({}, VOTE_VERIFIED))
    assert audit.recomputed_verdict == VOTE_UNKNOWN
    assert audit.notes == ["hiç_oy_yok"]
    assert audit.quorum_met is False


# ---------------------------------------------------------- 2 · yeter sayı
def test_quorum_unmet_flags_single_seat_and_downgrades_verdict(monkeypatch):
    monkeypatch.setenv("PINEAL_JURY_QUORUM", "3")
    audit = audit_claim(_FakeResult({"a": VOTE_VERIFIED, "b": VOTE_VERIFIED}, VOTE_VERIFIED))
    assert audit.quorum_required == 3
    assert audit.quorum_met is False
    assert audit.recomputed_verdict == VOTE_UNKNOWN  # yeter sayı yok
    assert audit.agreement is False
    assert any("yeter_sayı_yok" in note for note in audit.notes)


def test_single_seat_is_marked_as_not_consensus(monkeypatch):
    monkeypatch.setenv("PINEAL_JURY_QUORUM", "1")
    audit = audit_claim(_FakeResult({"a": VOTE_VERIFIED}, VOTE_VERIFIED))
    assert audit.quorum_met is True
    assert "tek_koltuk_konsensüs_değil" in audit.notes


def test_quorum_default_is_one_and_binding_default_off(monkeypatch):
    monkeypatch.delenv("PINEAL_JURY_QUORUM", raising=False)
    monkeypatch.delenv("PINEAL_JURY_BINDING", raising=False)
    assert quorum() == 1
    assert binding_enabled() is False


def test_invalid_quorum_falls_back_to_one(monkeypatch):
    monkeypatch.setenv("PINEAL_JURY_QUORUM", "çok")
    assert quorum() == 1


# ----------------------------------------------------- 3 · özet ve görünürlük
def test_summary_counts_mismatches_and_strength(monkeypatch):
    monkeypatch.delenv("PINEAL_JURY_BINDING", raising=False)
    reports = [
        audit_claim(_FakeResult({"a": VOTE_VERIFIED, "b": VOTE_VERIFIED}, VOTE_VERIFIED, "c1")),
        audit_claim(_FakeResult({"a": VOTE_VERIFIED, "b": VOTE_FALSE}, VOTE_VERIFIED, "c2")),
    ]
    summary = summarize(reports)
    assert summary.claims_audited == 2
    assert summary.mismatches == 1
    assert summary.mismatch_claims == ["c2"]
    assert summary.single_seat_claims == 0
    assert 0.0 <= summary.mean_strength <= 1.0
    assert "KONSENSÜS" in summary.machine_note


def test_empty_summary_is_honest():
    summary = summarize([])
    assert summary.claims_audited == 0
    assert summary.mismatches == 0
    assert "denetlenecek iddia yok" in summary.machine_note


# ------------------------------------------------------------ 4 · bağlayıcı kip
def test_binding_mode_downgrades_mismatching_claims(monkeypatch):
    monkeypatch.setenv("PINEAL_JURY_BINDING", "true")
    reports = [
        audit_claim(_FakeResult({"a": VOTE_VERIFIED, "b": VOTE_FALSE}, VOTE_VERIFIED, "c1")),
        audit_claim(_FakeResult({"a": VOTE_VERIFIED, "b": VOTE_VERIFIED}, VOTE_VERIFIED, "c2")),
    ]
    downgrades = consensus_downgrades(reports)
    assert downgrades == {"c1": VOTE_UNKNOWN}


def test_non_binding_mode_never_changes_verdicts(monkeypatch):
    monkeypatch.delenv("PINEAL_JURY_BINDING", raising=False)
    reports = [
        audit_claim(_FakeResult({"a": VOTE_VERIFIED, "b": VOTE_FALSE}, VOTE_VERIFIED, "c1"))
    ]
    assert consensus_downgrades(reports) == {}


# ---------------------------------------------------------- 5 · determinizm
def test_audit_is_deterministic(monkeypatch):
    monkeypatch.delenv("PINEAL_JURY_QUORUM", raising=False)
    result = _FakeResult({"a": VOTE_VERIFIED, "b": VOTE_FALSE, "c": VOTE_VERIFIED}, VOTE_VERIFIED)
    first = audit_claim(result).model_dump()
    second = audit_claim(result).model_dump()
    assert first == second  # rastgelelik/LLM yok


# ------------------------------------------- 6 · doğrulayıcıya gerçekten bağlı
@pytest.mark.asyncio
async def test_full_verifier_run_publishes_consensus(monkeypatch):
    """Panel kararından sonra denetçi ÇALIŞIR ve sonucu rapora yazar."""
    monkeypatch.delenv("PINEAL_JURY_BINDING", raising=False)
    monkeypatch.delenv("PINEAL_JURY_QUORUM", raising=False)
    from agent_core.agents.autonomous_verifier import AutonomousVerifier
    from test_verifier_jury_panel import _FakeSearch, _PanelGateway  # type: ignore

    gw = _PanelGateway(
        verdicts={"pineal_juror_google": VOTE_VERIFIED, "pineal_juror_open": VOTE_VERIFIED},
        extract_claims=["Kıdemli Stratejist"],
    )
    verifier = AutonomousVerifier(search_engine=_FakeSearch())

    report = await verifier.execute({"target_profile": {"bio": "Kıdemli Stratejist", "name": "Ada"}}, None, gw)

    assert report.consensus is not None, "denetçi raporu yok — B1 kablolu değil"
    assert report.consensus["claims_audited"] >= 1
    assert report.consensus["mismatches"] == 0
    assert report.consensus["binding"] is False
    assert "konsensüs:" in report.decision_rule
    assert report.consensus_downgrades == {}


@pytest.mark.asyncio
async def test_binding_consensus_rewrites_verdict_in_real_run(monkeypatch):
    """Bağlayıcı kipte uyuşmazlık hükmü DÜŞÜRÜR: rapor BİLİNMİYOR'a çekilir."""
    monkeypatch.setenv("PINEAL_JURY_BINDING", "true")
    monkeypatch.setenv("PINEAL_JURY_QUORUM", "3")
    from agent_core.agents.autonomous_verifier import AutonomousVerifier
    from test_verifier_jury_panel import _FakeSearch, _PanelGateway  # type: ignore

    # İki koltuk aynı yöne oy verir; panel "çoğunluk" der. Denetçi ise
    # yeter sayının (3) altında kaldığını görür: hüküm konsensüs değildir.
    gw = _PanelGateway(
        verdicts={"pineal_juror_google": VOTE_VERIFIED, "pineal_juror_open": VOTE_VERIFIED},
        extract_claims=["Kıdemli Stratejist"],
    )
    verifier = AutonomousVerifier(search_engine=_FakeSearch())

    report = await verifier.execute({"target_profile": {"bio": "Kıdemli Stratejist", "name": "Ada"}}, None, gw)

    assert report.consensus["binding"] is True
    assert report.consensus["quorum_met_claims"] == 0
    assert report.consensus_downgrades, "yeter sayı altındaki hüküm düşürülmedi"
    assert report.status != "VERIFIED", "yeter sayı yokken VERIFIED geçti"
    assert report.verifications[0].truth_status == VOTE_UNKNOWN
    assert report.unknown_claims >= 1
    assert "bağlayıcı=evet" in report.decision_rule
