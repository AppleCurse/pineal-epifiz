"""[RÖNTGEN 2026-09-23] Kanıt kapısı (entailment/provenance) — jüri beyanı yetmez.

Ölçülen eski davranış (probe: docs/reports/HALUSINASYON_ZINCIRI_DENETIMI_2026-09-23.md):

  * Arama sonucu `https://gercek-kaynak.test` dönerken jüri koltuğu
    `evidence_url="https://UYDURMA-kaynak.test"` yazdı → rapor
    `status=VERIFIED, confidence=1.0, overall_authenticity_score=1.0`.
    Kaynağın iddiayı destekleyip desteklemediğini zorunlu doğrulayan katman YOKTU.
  * 10 iddianın yalnız 1'i kesinleşti, 9'u BİLİNMİYOR kaldı →
    `status=VERIFIED, confidence=0.70` (güven tabanı `max(conclusive/total, 0.70)`).
  * Hiçbir iddia kesinleşmedi → `status=UNVERIFIED, confidence=0.70,
    data_confidence=True` ve UncertaintyEngine bunu `is_suspicious=False`
    ("Güvenili") diye geçirdi: fail-closed zincir taban yüzünden delikti.
  * Jüri "Doğrulandı!" / "verified" gibi sözlük dışı oy döndürdüğünde oy ham
    hâlde kayda geçiyor, hiçbir sınıfa sayılmıyordu (sessiz veri kaybı).

Bu dosya yeni sözleşmeyi kilitler: kapı yalnız onayı DÜŞÜREBİLİR, asla onay
ÜRETEMEZ; güven tabansızdır; belirsiz iddia VERIFIED'i engeller; sözlük dışı
oy onaya dönüşmez.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_core.agents.autonomous_verifier import (
    AutonomousVerifier,
    VerificationResult,
    canonical_vote,
    claim_support_ratio,
)
from agent_core.services.uncertainty_engine import UncertaintyEngine

PROMPT = "<UNTRUSTED_CLAIM>Kıdemli Stratejist</UNTRUSTED_CLAIM>"
CLAIM = "Kıdemli Stratejist"
REAL_URL = "https://gercek-kaynak.test/haber/ada"
REAL_TEXT = "Ada Yılmaz şirketin kıdemli stratejist olarak çalışıyor"
SOURCES = [(REAL_URL, REAL_TEXT)]


class _Gateway:
    """Jüri koltuklarına istenen yanıtı koyan sahte gateway."""

    def __init__(self, votes: dict | None = None, claims: list | None = None,
                 evidence_url: str = REAL_URL, evidence_quote: str = "kıdemli stratejist olarak çalışıyor",
                 contradiction_detail: str = "Kaynak unvanı stratejist değil, operasyon sorumlusu olarak veriyor"):
        self.votes = votes or {}
        self.claims = claims or [CLAIM]
        self.evidence_url = evidence_url
        self.evidence_quote = evidence_quote
        self.contradiction_detail = contradiction_detail
        self.calls: list[str] = []

    def get_agent_chain(self, agent_name, task):
        if agent_name == "autonomous_verifier":
            return ["anthropic/claude-sonnet-5"]
        raise KeyError(agent_name)

    async def query_json_chain(self, prompt, schema, task="depth", **kwargs):
        agent_name = kwargs.get("agent_name")
        self.calls.append(agent_name or f"task:{task}")
        if agent_name == "autonomous_verifier_extract":
            from agent_core.agents.autonomous_verifier import Claim

            return SimpleNamespace(claims=[Claim(claim_text=c, category="meslek") for c in self.claims])
        raw = self.votes.get(agent_name, "BİLİNMİYOR")
        return VerificationResult(
            claim_text=CLAIM, truth_status=raw,
            evidence_url=self.evidence_url, evidence_quote=self.evidence_quote,
            contradiction_detail=self.contradiction_detail,
        )


class _Search:
    tavily_key = "k"
    serpapi_key = None
    exa_key = None

    def __init__(self, url: str = REAL_URL, text: str = REAL_TEXT, results: int = 1):
        self.url, self.text, self.results = url, text, results

    async def search(self, query, num_results=2):
        return SimpleNamespace(
            available=True,
            results=[
                SimpleNamespace(source_url=self.url, content=self.text) for _ in range(self.results)
            ],
        )


def _verifier(search=None) -> AutonomousVerifier:
    return AutonomousVerifier(search_engine=search or _Search())


# --------------------------------------------------------------------------- #
# 1) UYDURMA KANIT URL'Sİ ONAY ÜRETEMEZ
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_fabricated_evidence_url_cannot_verify():
    """Jüri, arama sonucunda OLMAYAN bir adresi kanıt diye yazarsa oy düşer."""
    gw = _Gateway(
        votes={"pineal_juror_google": "DOĞRULANDI", "pineal_juror_open": "DOĞRULANDI"},
        evidence_url="https://uydurma-kaynak.test/yok-boyle-sayfa",
    )
    report = await _verifier().execute({"target_profile": {"bio": "Kıdemli Stratejist", "name": "Ada"}}, None, gw)

    assert report.status == "UNVERIFIED", "uydurma kanıt URL'si VERIFIED üretti"
    assert report.confidence == 0.0
    assert report.data_confidence is False
    assert report.fallback_reason == "no_conclusive_evidence"
    claim = report.verifications[0]
    assert claim.truth_status == "BİLİNMİYOR"
    assert set(claim.vote_audit.values()) == {"kanit_url_kaynaksiz"}
    assert claim.evidence_url == "", "uydurma URL rapora kanıt diye yazıldı"


@pytest.mark.asyncio
async def test_gate_blocks_single_seat_approval_too(monkeypatch):
    """Tek koltuklu panelde de kapı geçerlidir (koltuk sayısı onayı gevşetmez)."""
    monkeypatch.setattr(AutonomousVerifier, "PANEL_AGENTS", ("pineal_juror_google",))
    gw = _Gateway(votes={"pineal_juror_google": "DOĞRULANDI"}, evidence_url="https://baska.test")
    result = await _verifier()._verify_with_panel(PROMPT, CLAIM, gw, sources=SOURCES)

    assert result.truth_status == "BİLİNMİYOR"
    assert result.vote_audit["pineal_juror_google"] == "kanit_url_kaynaksiz"


# --------------------------------------------------------------------------- #
# 2) ALINTI KAYNAKTA BİREBİR YOKSA ONAY DÜŞER (QuoteGuard aynı kural)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_quote_must_exist_verbatim_in_source():
    gw = _Gateway(
        votes={"pineal_juror_google": "DOĞRULANDI", "pineal_juror_open": "DOĞRULANDI"},
        evidence_quote="kendi cümlemle özet: kişi üst düzey bir yönetici olabilir",
    )
    result = await _verifier()._verify_with_panel(PROMPT, CLAIM, gw, sources=SOURCES)

    assert result.truth_status == "BİLİNMİYOR"
    assert set(result.vote_audit.values()) == {"kanit_alinti_kaynaksiz"}


@pytest.mark.asyncio
async def test_claim_not_supported_by_source_is_not_verified():
    """Kaynak gerçek, alıntı gerçek — ama iddiayla ilgisi yok (destek oranı)."""
    gw = _Gateway(
        votes={"pineal_juror_google": "DOĞRULANDI", "pineal_juror_open": "DOĞRULANDI"},
        claims=["Havacılık ve Uzay Mühendisi"],
        evidence_quote="Ada Yılmaz şirketin kıdemli stratejist olarak çalışıyor",
    )
    # Arama sonucu "stratejist" diyor; iddia "havacılık/uzay mühendisi".
    report = await _verifier().execute(
        {"target_profile": {"bio": "Havacılık ve Uzay Mühendisi", "name": "Ada"}}, None, gw
    )

    assert report.status == "UNVERIFIED"
    assert report.confidence == 0.0
    audit = report.verifications[0].vote_audit
    assert all(rule.startswith("kanit_destek_orani_dusuk") for rule in audit.values())


def test_support_ratio_is_deterministic_and_bounded():
    assert claim_support_ratio("Kıdemli Stratejist", REAL_TEXT) == 1.0
    assert claim_support_ratio("Havacılık ve Uzay Mühendisi", REAL_TEXT) == 0.0
    assert claim_support_ratio("", REAL_TEXT) == 0.0
    assert claim_support_ratio("Kıdemli Stratejist", "") == 0.0


# --------------------------------------------------------------------------- #
# 3) KAPIDAN GEÇEN KANIT ONAY ÜRETİR (kapı her şeyi reddetmiyor)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_real_source_quote_and_support_yields_verified():
    gw = _Gateway(votes={"pineal_juror_google": "DOĞRULANDI", "pineal_juror_open": "DOĞRULANDI"})
    report = await _verifier().execute({"target_profile": {"bio": "Kıdemli Stratejist", "name": "Ada"}}, None, gw)

    assert report.status == "VERIFIED"
    assert report.confidence == 1.0
    assert report.data_confidence is True
    claim = report.verifications[0]
    assert claim.evidence_url == REAL_URL, "gerçek kaynak URL'si rapora yazılmalı"
    assert claim.evidence_quote, "kanıt alıntısı raporda durmalı"
    assert all(rule.startswith("kanit_kapisi_gecildi") for rule in claim.vote_audit.values())
    assert claim.claim_id and claim.claim_id.startswith("clm_")
    assert claim.claim_origin == "bio_extracted"
    assert claim.claim_source_refs == ["target_profile.bio"]
    assert claim.direct_refutation_confirmed is False


# --------------------------------------------------------------------------- #
# 4) GÜVEN TABANI YOK: belirsiz oy VERIFIED'i ve yüksek güveni engelleyemez
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_uncertain_claims_block_verified_verdict():
    """1 kesin + 9 belirsiz → eskiden VERIFIED/0.70; artık PARTIALLY_VERIFIED."""
    class _PartialGateway(_Gateway):
        async def query_json_chain(self, prompt, schema, task="depth", **kwargs):
            agent_name = kwargs.get("agent_name")
            self.calls.append(agent_name or f"task:{task}")
            if agent_name == "autonomous_verifier_extract":
                from agent_core.agents.autonomous_verifier import Claim

                return SimpleNamespace(claims=[Claim(claim_text=c, category="m") for c in self.claims])
            # Yalnız ilk iddia (prompt'ta geçen) DOĞRULANDI, diğerleri BİLİNMİYOR.
            first = CLAIM in prompt
            raw = self.votes.get(agent_name, "BİLİNMİYOR") if first else "BİLİNMİYOR"
            return VerificationResult(claim_text=CLAIM, truth_status=raw,
                                      evidence_url=REAL_URL, evidence_quote=self.evidence_quote)

    claims = [CLAIM] + [f"bilinmeyen iddia {i}" for i in range(9)]
    gw = _PartialGateway(
        votes={"pineal_juror_google": "DOĞRULANDI", "pineal_juror_open": "DOĞRULANDI"},
        claims=claims,
    )
    report = await _verifier().execute({"target_profile": {"bio": "b", "name": "Ada"}}, None, gw)

    assert report.status == "PARTIALLY_VERIFIED", "belirsiz iddialar VERIFIED'i engellemeli"
    assert report.unknown_claims == 9
    assert report.confidence == 0.1, "güven tabanı (0.70) geri geldi"
    assert report.overall_authenticity_score == 0.1


@pytest.mark.asyncio
async def test_no_conclusive_evidence_confidence_is_zero_and_fail_closed():
    gw = _Gateway()  # tüm koltuklar BİLİNMİYOR
    report = await _verifier().execute({"target_profile": {"bio": "Kıdemli Stratejist", "name": "Ada"}}, None, gw)

    assert report.status == "UNVERIFIED"
    assert report.confidence == 0.0, "kanıt yokken güven 0.70 tabanına sabitlenemez"
    assert report.data_confidence is False
    assert report.fallback_reason == "no_conclusive_evidence"

    # Fail-closed zincir: UncertaintyEngine artık "Güvenli" diyemez.
    check = UncertaintyEngine().evaluate(report, "autonomous_verifier")
    assert check.is_suspicious is True
    assert check.confidence < 0.65, "eşik altı güven tamponlanamaz"


def test_confidence_has_no_floor_in_source():
    import pathlib

    source = pathlib.Path("agent_core/agents/autonomous_verifier.py").read_text(encoding="utf-8")
    assert "max(conclusive / total, 0.70)" not in source, "güven tabanı geri geldi"
    # Rapor güveni yalnız ölçülen iki orandan türer (kesinlik × uzlaşma).
    assert "(conclusive / total) * agreement" in source


# --------------------------------------------------------------------------- #
# 5) OY SÖZLÜĞÜ KAPALI: sözlük dışı metin asla onaya dönüşmez
# --------------------------------------------------------------------------- #
def test_vote_vocabulary_is_closed():
    assert canonical_vote("DOĞRULANDI") == "DOĞRULANDI"
    assert canonical_vote(" doğrulandı! ") == "DOĞRULANDI"
    assert canonical_vote("Dogrulandi") == "DOĞRULANDI"
    assert canonical_vote("verified") == "DOĞRULANDI"
    assert canonical_vote("ÇELİŞKİLİ") == "ÇELİŞKİLİ"
    assert canonical_vote("YALAN") == "YALAN"
    assert canonical_vote("BİLİNMİYOR") == "BİLİNMİYOR"
    assert canonical_vote("") == "BİLİNMİYOR"
    # Aksan/noktalama/büyük-küçük harf farkı oyu GEÇERSİZ kılmaz.
    assert canonical_vote("Doğrulandı!") == "DOĞRULANDI"
    # Sözlük dışı: onay YOK, geçersiz oy olarak kayda geçer.
    for bogus in ("KESİNLİKLE DOĞRU", "verified gibi", "probably", "YES", "42", None, 1):
        assert canonical_vote(bogus) is None, bogus


@pytest.mark.asyncio
async def test_invalid_vote_text_never_approves_and_is_recorded():
    """Sözlük dışı oy ('kesinlikle doğru', 'verified gibi') onaya dönüşmez.

    Not: büyük/küçük harf, aksan ve noktalama farkları GEÇERSİZ oy değildir
    ("Doğrulandı!" → DOĞRULANDI); kapı onayı kanıtla sınar. Sözlükte hiç
    olmayan bir ifade ise asla sınıflandırılmaz — kayda 'invalid' geçer.
    """
    gw = _Gateway(votes={"pineal_juror_google": "KESİNLİKLE DOĞRU", "pineal_juror_open": "verified gibi"})
    report = await _verifier().execute({"target_profile": {"bio": "Kıdemli Stratejist", "name": "Ada"}}, None, gw)

    claim = report.verifications[0]
    assert claim.truth_status == "BİLİNMİYOR"
    assert claim.invalid_votes == {"pineal_juror_google": "KESİNLİKLE DOĞRU", "pineal_juror_open": "verified gibi"}
    assert report.status == "UNVERIFIED"
    assert report.confidence == 0.0
    assert report.vote_accounting["invalid"] == 2


# --------------------------------------------------------------------------- #
# 6) KOLTUK HATASI SESSİZ YUTULMAZ
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_seat_failure_is_recorded_not_swallowed():
    class _FailingGateway(_Gateway):
        async def query_json_chain(self, prompt, schema, task="depth", **kwargs):
            agent_name = kwargs.get("agent_name")
            self.calls.append(agent_name)
            if agent_name == "autonomous_verifier_extract":
                return await super().query_json_chain(prompt, schema, task, **kwargs)
            if agent_name == "pineal_juror_google":
                raise RuntimeError("upstream 503")
            return await super().query_json_chain(prompt, schema, task, **kwargs)

    gw = _FailingGateway(votes={"pineal_juror_open": "DOĞRULANDI"})
    result = await _verifier()._verify_with_panel(PROMPT, CLAIM, gw, sources=SOURCES)

    assert "pineal_juror_google" in result.seat_errors
    assert "503" in result.seat_errors["pineal_juror_google"]
    assert result.truth_status == "DOĞRULANDI"  # tek geçerli koltuk kararı verir
    assert result.decision_rule.startswith("tek_juri:pineal_juror_open")
    assert "koltuk_hatasi=pineal_juror_google" in result.decision_rule


# --------------------------------------------------------------------------- #
# 7) KAPI YALANLAMAYI DA KANITA BAĞLAR (tek yönlü değil)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_falsification_also_requires_real_source():
    gw = _Gateway(
        votes={"pineal_juror_google": "YALAN", "pineal_juror_open": "YALAN"},
        evidence_url="https://uydurma.test",
    )
    result = await _verifier()._verify_with_panel(PROMPT, CLAIM, gw, sources=SOURCES)

    assert result.truth_status == "BİLİNMİYOR", "kaynaksız yalanlama da hüküm olamaz"
    assert set(result.vote_audit.values()) == {"kanit_url_kaynaksiz"}


@pytest.mark.asyncio
async def test_negative_vote_without_reason_is_not_counted():
    """Yalanlama GEREKÇESİZ olamaz: çelişkiyi anlatmayan oy kanıt değildir."""
    gw = _Gateway(
        votes={"pineal_juror_google": "YALAN", "pineal_juror_open": "YALAN"},
        contradiction_detail="",
    )
    result = await _verifier()._verify_with_panel(PROMPT, CLAIM, gw, sources=SOURCES)

    assert result.truth_status == "BİLİNMİYOR"
    assert set(result.vote_audit.values()) == {"celiski_gerekcesi_yok"}


@pytest.mark.asyncio
async def test_falsification_with_real_source_stands():
    gw = _Gateway(votes={"pineal_juror_google": "YALAN", "pineal_juror_open": "YALAN"})
    report = await _verifier().execute({"target_profile": {"bio": "Kıdemli Stratejist", "name": "Ada"}}, None, gw)

    assert report.status == "CONTRADICTED"
    assert report.overall_authenticity_score == 0.0
