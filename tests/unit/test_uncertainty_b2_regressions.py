"""P1-B2: uncertainty_engine uzunluk-bağımsızlık regresyonları.

Kural: karakter sayısı confidence ÜRETMEZ.
- boş -> 0, dolu ve şema-geçerli -> sabit completeness katkısı
- aynı semantik içeriğin 24/64/160 karakter varyantları karar DEĞİŞTİRMEMELİ
- makul KISA ama geçerli profil HALT olmamalı
- boş/kanıtsız profil PASS olmamalı
- şemada olmayan ekstra alanlar confidence'i YÜKSELTMEMELİ
"""

import pytest

from agent_core.agents.mirror_truth import MirrorReflection
from agent_core.domain.memory_models import PassionProfile
from agent_core.services.uncertainty_engine import UncertaintyEngine


def _realistic_short_passion() -> PassionProfile:
    """Gerçek Pydantic şemasına uygun, ekstra alansız, makul KISA profil."""
    return PassionProfile(
        core_passions=["Mimari", "Analog fotografi"],
        energizing_topics=["Sokak cekimleri"],
        flow_triggers=["Kahve"],
        sentiment_polarity=0.7,
        evidence_quotes=["Estetik her seydir."],
        confidence=0.85,
        data_confidence=True,
    )


def _mirror_with_padded_strings(char_budget: int) -> MirrorReflection:
    """Aynı semantiği tekrarla doldurarak yaklaşık N karaktere çıkar.

    (Padding burada PROBE'dur: test yalnızca uzunluğun kararı değiştirmediğini
    kanıtlar; padding'in kendisi artık skoru yükseltemez.)
    """
    unit = "frekans "
    n = max(1, char_budget // len(unit))
    return MirrorReflection(
        user_core_frequency=(unit * n).strip(),
        surface_persona=(unit * n).strip(),
        alignment_score=0.8,
        authentic_anchors=["capa bir", "capa iki", "capa uc"],
        confidence=0.9,
        data_confidence=True,
    )


def test_realistic_short_passion_profile_passes_gate():
    """B1+B2 kapısı: makul KISA ve şema-uyumlu PassionProfile HALT olmamalı."""
    engine = UncertaintyEngine()
    report = engine.evaluate(_realistic_short_passion(), "passion_mapper")
    assert not report.is_suspicious, report.reason
    assert report.confidence >= 0.70, report.confidence


def test_empty_passion_profile_does_not_pass():
    """B1+B2 kapısı: boş/kanıtsız profil PASS olmamalı."""
    engine = UncertaintyEngine()
    empty = PassionProfile(
        core_passions=[],
        energizing_topics=[],
        flow_triggers=[],
        sentiment_polarity=0.0,
        evidence_quotes=[],
        confidence=0.2,
    )
    report = engine.evaluate(empty, "passion_mapper")
    assert report.is_suspicious, report.reason
    assert report.confidence < 0.70, report.confidence


def test_extra_fields_do_not_raise_confidence():
    """B2: şemada olmayan alanlar confidence'i yükseltmemeli."""
    engine = UncertaintyEngine()
    base = _realistic_short_passion()
    inflated = base.model_copy(update={
        "passion_categories": ["X", "Y"],
        "intensity_indicators": ["Z"],
        "anti_passions": ["W"],
        "evidence_strength": "Güçlü",
    })
    r_base = engine.evaluate(base, "passion_mapper")
    r_inflated = engine.evaluate(inflated, "passion_mapper")
    assert r_base.confidence == r_inflated.confidence, (r_base, r_inflated)


def test_string_length_variants_do_not_change_mirror_verdict():
    """B2 regresyon: 24/64/160 karakter varyantları HALT<->PASS DEĞİŞTİRMEMELİ."""
    engine = UncertaintyEngine()
    verdicts = {}
    for n in (3, 8, 20):  # ~24 / ~64 / ~160 karakter
        report = engine.evaluate(_mirror_with_padded_strings(n * 8), "mirror_truth")
        verdicts[n] = (report.is_suspicious, round(report.confidence, 6))
    # Üç uzunlukta da birebir AYNI karar ve AYNI güven
    assert len(set(verdicts.values())) == 1, verdicts
    assert verdicts[3] == (False, 0.9), verdicts


def test_short_valid_mirror_answer_does_not_halt():
    """B2: ~30 karakterlik geçerli cevap sırf kısa diye HALT olmamalı."""
    engine = UncertaintyEngine()
    result = MirrorReflection(
        user_core_frequency="derin tasarim ve estetik",
        surface_persona="analitik ve olculu",
        alignment_score=0.8,
        authentic_anchors=["estetik", "mekan", "yuruyus"],
        confidence=0.9,
        data_confidence=True,
    )
    report = engine.evaluate(result, "mirror_truth")
    assert not report.is_suspicious, report.reason
    assert report.confidence >= 0.70, report.confidence


def test_string_score_is_constant_not_length_based():
    """B2: string skoru sabit katkıdır; 1 karakter ile 200 karakter aynı."""
    engine = UncertaintyEngine()
    one_char = engine._score_field_value("a", empty_list_penalty=0.12)
    two_hundred = engine._score_field_value("x" * 200, empty_list_penalty=0.12)
    whitespace = engine._score_field_value("   ", empty_list_penalty=0.12)
    missing = engine._score_field_value("veri bulunamadı", empty_list_penalty=0.12)
    assert one_char == two_hundred == 1.0
    assert whitespace == 0.0
    assert missing == 0.0


def test_list_score_is_constant_not_length_based():
    """B2: dolu liste sabit katkıdır; kısa/uzun eleman fark yaratmaz."""
    engine = UncertaintyEngine()
    short_items = engine._score_field_value(["a"], empty_list_penalty=0.12)
    long_items = engine._score_field_value(["x" * 300], empty_list_penalty=0.12)
    empty = engine._score_field_value([], empty_list_penalty=0.12)
    assert short_items == long_items == 1.0
    assert empty == 0.12


@pytest.mark.asyncio
async def test_mirror_of_truth_preserves_zero_model_confidence():
    """A model confidence of zero is not raised to a fabricated floor."""
    from unittest.mock import AsyncMock
    from agent_core.agents.mirror_truth import MirrorOfTruth, MirrorReflection

    mock_gateway = AsyncMock()
    mock_gateway.query_json_chain = AsyncMock(return_value=MirrorReflection(
        user_core_frequency="ambient_fotograf_gece",
        surface_persona="Sessiz ve estetik gozlemci",
        alignment_score=0.88,
        authentic_anchors=["fotograf_anchor", "gece_anchor"],
        confidence=0.0,
    ))

    agent = MirrorOfTruth(llm_gateway=mock_gateway)
    res = await agent.execute({
        "user_profile": {
            "private_rituals": ["gece okumalari", "fotograf"],
            "late_night_playlist": ["ambient", "caz"],
            "secret_envies": ["sahici diyalog"],
        }
    })

    assert res.confidence == 0.0
    assert res.data_confidence is False
    assert res.fallback_reason == "model_confidence_zero"

    engine = UncertaintyEngine()
    report = engine.evaluate(res, "mirror_truth")
    assert report.is_suspicious
    assert report.confidence == 0.0

