"""`data_confidence=False` kapısının dürüstlüğü (adım 1: nihai rapor bacağı).

Sözleşme: bir ajan çıktısını "veri güvenim yok" diye işaretlediyse, o çıktı
KARAR sayılmaz. `UncertaintyEngine.evaluate` bu durumda:
  * genel ajanlar -> is_suspicious=True, confidence=0.0, fail-closed
    ("Kaynak verisi kullanılamıyor; fallback sonuç kabul edilmedi.")
  * resonance_calc -> görev akışını durdurmaz ama gerekçe metni çıktının
    KARAR olmadığını söyler (aşağıdaki BİLİNEN TABAN notuyla).

Yeniden ölçülen eski kusur: uydurma kanıt URL'li, elle VERIFIED yazılmış bir
VerifierReport "Güvenli / 0.75" alıyordu. Verifier tarafı artık böyle bir
rapor ÜRETEMİYOR (kanıt kapısı oyu iptal eder, data_confidence=False yazar);
bu dosya ise downstream kapının (UncertaintyEngine) da fail-closed olduğunu
kilitler.
"""

from __future__ import annotations

import pytest

from agent_core.agents.autonomous_verifier import VerificationResult, VerifierReport
from agent_core.services.uncertainty_engine import UncertaintyEngine


def _honest_unverified_report() -> VerifierReport:
    """Verifier'ın kanıt bulunamadığında GERÇEKTEN ürettiği rapor biçimi."""
    return VerifierReport(
        verifications=[
            VerificationResult(
                claim_text="Kıdemli Stratejist",
                truth_status="BİLİNMİYOR",
                evidence_url="",
                contradiction_detail="",
                juror_votes={"pineal_juror_google": "BİLİNMİYOR", "pineal_juror_open": "BİLİNMİYOR"},
                decision_rule="panel_cogunluk",
            )
        ],
        overall_authenticity_score=0.0,
        status="UNVERIFIED",
        confidence=0.0,
        jurors=["pineal_juror_google", "pineal_juror_open"],
        decision_rule="panel:panel_cogunluk",
        data_confidence=False,
        fallback_reason="no_conclusive_evidence",
        unknown_claims=1,
    )


def test_unverified_verifier_report_is_not_safe_evidence():
    """Kanıt yoksa 'Güvenli' hükmü çıkamaz (eski kusur: 0.70 taban + Güvenli)."""
    report = _honest_unverified_report()
    result = UncertaintyEngine().evaluate(report, "autonomous_verifier")

    assert result.is_suspicious is True
    assert result.confidence == 0.0
    assert "fallback" in result.reason or "kullanılamıyor" in result.reason


def test_data_confidence_false_never_yields_guvenli_reason():
    report = _honest_unverified_report()
    result = UncertaintyEngine().evaluate(report, "autonomous_verifier")
    assert result.reason != "Güvenli"


@pytest.mark.parametrize(
    "comp_score",
    [0.0, 0.42, 0.91],
)
def test_resonance_calc_failclosed_reason_admits_it_is_not_a_decision(comp_score):
    """resonance_calc: akış durmaz ama metin 'KARAR DEĞİL' demek zorunda.

    Eski kusur: confidence `max(0.75, comp_score)` olarak dönüyordu — yani
    ÖLÇÜLMEYEN bir güven uyduruluyor, executor'ın LOW_CONFIDENCE kapısı
    atlatılıyor ve gerekçe "Rezonans analizi tamamlandı" diyerek çıktı
    doğrulanmış bir karar gibi görünüyordu (RÖNTGEN §1.6).

    Tabanı kaldırmanın naif yolu (güven 0.0 => koşu `halted`) bu kez
    `state=inference_gap` bilgisini rapordan siliyordu. Uygulanan çözüm
    üçüncü durum: `no_decision=True` => executor koşuyu
    `completed_no_decision` olarak KAYBEDER (bkz.
    tests/unit/test_no_decision_run_status.py). GÖREV TAMAMLANDI ≠ KARAR
    ÜRETİLDİ.
    """
    from types import SimpleNamespace

    result_obj = SimpleNamespace(
        compatibility_score=comp_score,
        data_confidence=False,
        state="inference_gap",
        resonance_score=comp_score,
        decision_factors=[],
        rationale="vektör yok",
        approach="",
        confidence=comp_score,
        fallback_reason="vector_unavailable",
    )
    result = UncertaintyEngine().evaluate(result_obj, "resonance_calc")

    assert result.is_suspicious is False, "rezonans görev akışını durdurmaz"
    assert "KARAR DEĞİL" in result.reason
    assert "data_confidence=False" in result.reason
    # [RÖNTGEN 2026-09-23] Taban KALDIRILDI: güven = ölçülen değer, ayrım
    # artık `no_decision=True` ile yapılıyor (executor: completed_no_decision).
    assert result.no_decision is True
    assert result.confidence == comp_score
    assert "uydurulmadı" in result.reason
    assert "tamamlandı" not in result.reason, "eski sahte 'analiz tamamlandı' iddiası dönemez"


def test_legacy_data_confidence_true_does_not_escalate_to_verified_status():
    """Eski data_confidence=True, açık doğrulama kanıtı olmadan evidence_verification_status='verified' sayılmaz."""
    from agent_core.domain.memory_models import PassionProfile

    profile = PassionProfile(core_passions=["müzik"], confidence=0.8, data_confidence=True)
    report = UncertaintyEngine().evaluate(profile, "passion_mapper")
    assert report.input_data_present is True
    assert report.evidence_verification_status != "verified"
    assert report.evidence_verification_status in ("unverified", "unknown")


def test_input_data_present_false_fails_closed_even_if_data_confidence_flag_set():
    """input_data_present=False açıkça bildirildiyse data_confidence=True olsa bile fail-closed olmalı."""
    from types import SimpleNamespace

    fake_result = SimpleNamespace(
        core_passions=["müzik"],
        confidence=0.85,
        data_confidence=True,
        input_data_present=False,
        evidence_verification_status="unverified",
    )
    report = UncertaintyEngine().evaluate(fake_result, "passion_mapper")
    assert report.is_suspicious is True
    assert report.confidence == 0.0
    assert report.input_data_present is False
    assert report.evidence_verification_status == "unverified"
