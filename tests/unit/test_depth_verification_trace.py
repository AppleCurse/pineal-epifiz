"""[A-KAPANIŞ] Verifier → DepthAnalyst → DepthReport izlenebilirlik kilidi.

A1 ölçümünde bulunan kusur (2026-09-26): DepthAnalyst prompt'a verilen hakem
`evidence_quote`'unu birebir alıntılayıp çelişki üretiyordu; QuoteGuard korpusu
yalnız profil metinlerinden oluştuğu için bu KANITLI çelişki "uydurma alıntı"
sayılıp imha ediliyordu (dropped_fake_quote=1, contradictions=[]). Geriye yalnız
`reality_rationale` metni kalıyor, onda da hangi claim_id'nin kararı
değiştirdiği yapısal olarak izlenemiyordu.

Bu dosya iki cerrahi düzeltmeyi kilitler:
  1. quote_guard: kesin statülü hakem alıntıları meşru kaynak korpusudur.
  2. DepthFinding.source_claim_id / verification_status / verification_link_basis
     + DepthReport.verification_trace — statüyü yalnız kod yazar.
"""

import copy
import json

import pytest

from agent_core.agents.depth_analyst import DepthAnalyst, DepthFinding, DepthReport
from agent_core.services.quote_guard import (
    guard_report,
    verification_claim_index,
    verification_quote_anchors,
)

CLAIM_ID = "clm_0123456789abcdef0123"
OTHER_CLAIM_ID = "clm_fedcba9876543210fedc"
VERIFIER_QUOTE = "Acme Holding yönetim kurulu ve icra kadrosunda bu isim yer almamaktadır"

BASE_INPUT = {
    "target_profile": {
        "bio": "CEO @ Acme Holding | Girişimci",
        "posts": ["Yeni ofisimizden günaydın"],
    },
    "visual_evidence": {"detected_objects": ["ofis masası"]},
}


def _verifications(status="YALAN", quote=VERIFIER_QUOTE, claim_id=CLAIM_ID):
    return {
        "verifications": [
            {
                "claim_id": claim_id,
                "claim_origin": "bio_extracted",
                "claim_text": "CEO @ Acme Holding",
                "truth_status": status,
                "evidence_url": "https://acme.example/yonetim",
                "evidence_quote": quote,
                "direct_refutation_confirmed": status == "YALAN",
            }
        ],
        "canonical_observation_checks": [],
        "status": "PARTIALLY_VERIFIED",
    }


def _treatment_input(**kw):
    data = copy.deepcopy(BASE_INPUT)
    data["verifications"] = _verifications(**kw)
    return data


def _report_quoting_verifier():
    """LLM'in hakem alıntısına dayanarak ürettiği çelişki (A1 senaryosu)."""
    return {
        "reality_index": 0.25,
        "reality_rationale": "Bio'daki CEO unvanı hakem kaynağında yalanlandı.",
        "reality_findings": [
            {
                "topic": "Ofis",
                "observation": "Ofis ortamı paylaşımı var",
                "evidence_quotes": ["Yeni ofisimizden günaydın"],
            }
        ],
        "contradictions": [
            {
                "topic": "Acme CEO unvanı",
                "observation": "Bio CEO diyor; şirket kaydında isim yok",
                "evidence_quotes": [VERIFIER_QUOTE],
            }
        ],
        "essence_one_liner": "Vitrin unvanı kayıtla çelişiyor",
    }


# ---------------------------------------------------------------------------
# 1. Korpus: hakem alıntısı meşru kaynak
# ---------------------------------------------------------------------------

def test_a1_control_drops_verifier_quote_without_verifications():
    """CONTROL kolu: verifications yoksa korpus BİREBİR eski hâli — çelişki düşer."""
    cleaned, stats = guard_report(_report_quoting_verifier(), copy.deepcopy(BASE_INPUT))
    assert stats["dropped_fake_quote"] == 1
    assert cleaned["contradictions"] == []
    assert stats["verification_quote_sources"] == 0
    assert cleaned["verification_trace"]["claims_available"] == 0
    assert cleaned["verification_trace"]["linked_findings"] == []


def test_a1_treatment_keeps_and_links_verifier_anchored_contradiction():
    """TREATMENT kolu: aynı rapor, verifications var → çelişki ayakta + claim_id bağlı."""
    cleaned, stats = guard_report(_report_quoting_verifier(), _treatment_input())
    assert stats["dropped_fake_quote"] == 0
    assert stats["verification_quote_sources"] == 1
    assert stats["linked_to_verification"] == 1
    assert len(cleaned["contradictions"]) == 1

    c = cleaned["contradictions"][0]
    assert c["source_claim_id"] == CLAIM_ID
    assert c["verification_status"] == "YALAN"
    assert c["verification_link_basis"] == "quote_match"

    # Profil alıntısıyla ayakta kalan bulgu hakem iddiasına BAĞLANMAZ (sızma yok).
    f = cleaned["reality_findings"][0]
    assert f["source_claim_id"] is None
    assert f["verification_status"] is None

    trace = cleaned["verification_trace"]
    assert trace["claims_available"] == 1
    assert trace["quote_anchors"] == 1
    assert trace["claim_ids_used"] == [CLAIM_ID]
    assert trace["linked_findings"] == [
        {
            "section": "contradictions",
            "topic": "Acme CEO unvanı",
            "source_claim_id": CLAIM_ID,
            "verification_status": "YALAN",
            "link_basis": "quote_match",
        }
    ]


@pytest.mark.parametrize("status", ["BİLİNMİYOR", "", None, "verified", "Doğrulandı!"])
def test_non_conclusive_status_quote_is_not_an_anchor(status):
    """Kanıt kapısından geçmemiş (kesin olmayan / sözlük dışı) statünün alıntısı korpusa girmez."""
    data = _treatment_input(status=status)
    cleaned, stats = guard_report(_report_quoting_verifier(), data)
    assert stats["verification_quote_sources"] == 0
    assert stats["dropped_fake_quote"] == 1
    assert cleaned["contradictions"] == []
    # İddia yine de "bilinen kimlik" olarak sayılır (LLM claim_id'yi referans verebilir).
    assert cleaned["verification_trace"]["claims_available"] == 1
    assert cleaned["verification_trace"]["quote_anchors"] == 0


def test_canonical_observation_checks_are_never_anchors():
    """Kanonik gözlem kontrolleri olgusal hüküm taşımaz → korpus/indeks dışı."""
    data = copy.deepcopy(BASE_INPUT)
    data["verifications"] = {
        "verifications": [],
        "canonical_observation_checks": [
            {
                "claim_id": OTHER_CLAIM_ID,
                "claim_origin": "canonical_observation",
                "evidence_id": "ev_1",
                "claim_text": VERIFIER_QUOTE,
                "provenance_integrity": "missing",
                "factual_truth_status": "BİLİNMİYOR",
                "downstream_decision_state": "NO_FACTUAL_VERDICT",
            }
        ],
    }
    assert verification_claim_index(data) == {}
    cleaned, stats = guard_report(_report_quoting_verifier(), data)
    assert stats["verification_quote_sources"] == 0
    assert cleaned["contradictions"] == []


@pytest.mark.parametrize(
    "bad",
    [
        {"verifications": "not-a-dict"},
        {"verifications": {"verifications": "not-a-list"}},
        {"verifications": {"verifications": [{"claim_origin": "bio_extracted", "truth_status": "YALAN", "evidence_quote": VERIFIER_QUOTE}]}},  # claim_id yok
        {"verifications": {"verifications": [{"claim_id": "not-a-claim-id", "claim_origin": "bio_extracted", "truth_status": "YALAN", "evidence_quote": VERIFIER_QUOTE}]}},
        {"verifications": {"verifications": [{"claim_id": CLAIM_ID, "claim_origin": "other", "truth_status": "YALAN", "evidence_quote": VERIFIER_QUOTE}]}},
    ],
)
def test_malformed_or_foreign_verification_records_are_ignored(bad):
    data = copy.deepcopy(BASE_INPUT)
    data.update(bad)
    assert verification_quote_anchors(verification_claim_index(data)) == {}
    cleaned, stats = guard_report(_report_quoting_verifier(), data)
    assert stats["verification_quote_sources"] == 0
    assert cleaned["contradictions"] == []


# ---------------------------------------------------------------------------
# 2. Bağ ve statü: yalnız kod yazar
# ---------------------------------------------------------------------------

def test_llm_supplied_unknown_claim_id_is_rejected_but_finding_survives():
    report = _report_quoting_verifier()
    report["reality_findings"][0]["source_claim_id"] = "clm_00000000000000000000"
    report["reality_findings"][0]["verification_status"] = "YALAN"  # LLM statü uyduruyor
    cleaned, stats = guard_report(report, _treatment_input())

    f = cleaned["reality_findings"][0]
    assert f["topic"] == "Ofis"                      # bulgu düşmedi (profil alıntısı gerçek)
    assert f["source_claim_id"] is None              # bağ düştü
    assert f["verification_status"] is None          # LLM statüsü silindi
    assert f["verification_link_basis"] is None
    assert stats["rejected_claim_ids"] == 1
    assert cleaned["verification_trace"]["rejected_claim_ids"] == 1


def test_llm_supplied_valid_claim_id_gets_code_owned_status():
    """LLM claim_id'yi doğru referans verir ama statüyü yanlış yazar → kod ezer."""
    report = _report_quoting_verifier()
    report["contradictions"][0]["evidence_quotes"] = ["CEO @ Acme Holding"]  # bio alıntısı
    report["contradictions"][0]["source_claim_id"] = CLAIM_ID
    report["contradictions"][0]["verification_status"] = "DOĞRULANDI"        # yanlış
    cleaned, stats = guard_report(report, _treatment_input(status="YALAN"))

    c = cleaned["contradictions"][0]
    assert c["source_claim_id"] == CLAIM_ID
    assert c["verification_status"] == "YALAN"       # hakem kaydı kazanır
    assert c["verification_link_basis"] == "llm_claim_id"
    assert stats["linked_to_verification"] == 1
    assert stats["rejected_claim_ids"] == 0


def test_llm_status_without_any_link_is_erased():
    report = _report_quoting_verifier()
    report["reality_findings"][0]["verification_status"] = "DOĞRULANDI"
    cleaned, _ = guard_report(report, _treatment_input())
    assert cleaned["reality_findings"][0]["verification_status"] is None


def test_quote_match_link_uses_first_matching_claim_deterministically():
    data = copy.deepcopy(BASE_INPUT)
    data["verifications"] = {
        "verifications": [
            {**_verifications()["verifications"][0]},
            {**_verifications(claim_id=OTHER_CLAIM_ID, status="ÇELİŞKİLİ", quote="Kurucu ortak olarak 2021'de ayrıldı")["verifications"][0]},
        ]
    }
    report = _report_quoting_verifier()
    report["contradictions"].append(
        {
            "topic": "Kuruculuk",
            "observation": "Ortaklık geçmişte kalmış",
            "evidence_quotes": ["Kurucu ortak olarak 2021'de ayrıldı"],
        }
    )
    cleaned, stats = guard_report(report, data)
    assert stats["verification_quote_sources"] == 2
    assert [c["source_claim_id"] for c in cleaned["contradictions"]] == [CLAIM_ID, OTHER_CLAIM_ID]
    assert [c["verification_status"] for c in cleaned["contradictions"]] == ["YALAN", "ÇELİŞKİLİ"]
    assert cleaned["verification_trace"]["claim_ids_used"] == sorted([CLAIM_ID, OTHER_CLAIM_ID])


def test_rationale_claim_ids_and_anchoring_are_traced():
    report = _report_quoting_verifier()
    report["reality_rationale"] = (
        f'İddia {CLAIM_ID} hakemce YALAN: "{VERIFIER_QUOTE}". '
        f"Bilinmeyen kimlik clm_00000000000000000000 sayılmaz."
    )
    cleaned, stats = guard_report(report, _treatment_input())
    trace = cleaned["verification_trace"]
    assert trace["rationale_claim_ids"] == [CLAIM_ID]
    assert trace["rationale_anchored_to_verification"] is True
    assert "kaynak-alıntı doğrulanamadı" not in cleaned["reality_rationale"]
    assert stats.get("rationale_unverified") is None


def test_rationale_verifier_quote_is_unverified_in_control_arm():
    """Aynı gerekçe, verifications yokken 'doğrulanamadı' notu alır (eski davranış korunur)."""
    report = _report_quoting_verifier()
    report["reality_rationale"] = f'Hakem kaynağı: "{VERIFIER_QUOTE}".'
    cleaned, stats = guard_report(report, copy.deepcopy(BASE_INPUT))
    assert stats["rationale_unverified"] is True
    assert cleaned["verification_trace"]["rationale_anchored_to_verification"] is False


def test_legacy_stats_keys_unchanged():
    cleaned, stats = guard_report(_report_quoting_verifier(), copy.deepcopy(BASE_INPUT))
    for key in ("checked", "dropped_no_quote", "dropped_fake_quote", "dropped_topics", "kept"):
        assert key in stats
    assert stats["checked"] == 2 and stats["kept"] == 1


# ---------------------------------------------------------------------------
# 3. Uçtan uca: DepthAnalyst CONTROL vs TREATMENT (A1 impact testi, kalıcı)
# ---------------------------------------------------------------------------

class _FakeGateway:
    """Aynı LLM çıktısını iki kola da verir; fark yalnız input_data'dan gelir."""

    def __init__(self):
        self.prompts = []

    async def query_json_chain(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        return DepthReport(**_report_quoting_verifier())


@pytest.mark.asyncio
async def test_depth_analyst_control_vs_treatment_field_diff():
    gw = _FakeGateway()
    analyst = DepthAnalyst(llm_gateway=gw)

    control = await analyst.analyze(copy.deepcopy(BASE_INPUT), evidence_chain=[])
    treatment = await analyst.analyze(_treatment_input(), evidence_chain=[])

    # Prompt farkı: yalnız TREATMENT kolunda claim_id görünür.
    assert CLAIM_ID not in gw.prompts[0]
    assert CLAIM_ID in gw.prompts[1]

    # Alan bazlı diff (A1 tablosu):
    assert control.contradictions == []
    assert control.quote_guard["dropped_fake_quote"] == 1
    assert control.verification_trace["linked_findings"] == []

    assert len(treatment.contradictions) == 1
    assert treatment.quote_guard["dropped_fake_quote"] == 0
    linked = treatment.contradictions[0]
    assert isinstance(linked, DepthFinding)
    assert linked.source_claim_id == CLAIM_ID
    assert linked.verification_status == "YALAN"
    assert linked.verification_link_basis == "quote_match"
    assert treatment.verification_trace["claim_ids_used"] == [CLAIM_ID]

    # Serileşme: task_executor `status.depth_report = depth_rep.model_dump()`
    dumped = json.loads(json.dumps(treatment.model_dump(mode="json"), ensure_ascii=False))
    assert dumped["contradictions"][0]["source_claim_id"] == CLAIM_ID
    assert dumped["verification_trace"]["linked_findings"][0]["section"] == "contradictions"


@pytest.mark.asyncio
async def test_depth_analyst_fallback_report_has_no_trace_fields_set():
    class _Boom:
        async def query_json_chain(self, *a, **k):
            raise RuntimeError("llm down")

    rep = await DepthAnalyst(llm_gateway=_Boom()).analyze(_treatment_input(), evidence_chain=[])
    assert rep.reality_index == 0.0
    assert rep.verification_trace is None
    assert rep.contradictions == []


def test_depth_finding_schema_defaults_are_backward_compatible():
    f = DepthFinding(topic="t", observation="o")
    assert f.source_claim_id is None
    assert f.verification_status is None
    assert f.verification_link_basis is None
    r = DepthReport(reality_index=0.5, reality_rationale="", essence_one_liner="")
    assert r.verification_trace is None
