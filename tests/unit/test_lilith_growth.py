import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_core.agents.lilith_growth import (
    FreeTextGateway,
    LilithContentPackage,
    LilithGenerationResponse,
    LilithGrowthAgent,
    NeurochemicalProfile,
    NeuroMetrics,
    OpenAICompatibleGateway,
)


# --------------------------------------------------------------------------- #
# Mevcut Uçtan Uca Testler
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_lilith_growth_agent_execution():
    mock_gateway = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()

    mock_json = """{
      "hook": "Çoğu insan başarısızlıktan değil, parlamaktan korkar.",
      "psychological_angle": "Görünürlük kaygısı ve statü tehdidi",
      "content_body": "Gölgede kalmak konforludur. Ortaya çıktığınızda herkes sizi hedef alır.",
      "call_to_action": "Bu konfor alanını ne zaman terk edeceksiniz?",
      "pollinations_image_prompt": "cinematic dark moody photography of a silhouetted figure in spotlight",
      "dopamine": 0.8,
      "serotonin": 0.7,
      "cortisol": 0.6,
      "oxytocin": 0.5,
      "confidence": 0.95
    }"""
    mock_message.content = mock_json
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_gateway.chat = AsyncMock(return_value=mock_response)

    agent = LilithGrowthAgent(llm_gateway=mock_gateway)

    payload = {
        "topic": "Görünürlük Korkusu",
        "platform": "x_twitter",
        "target_profile": {
            "bio": "Kamuya açık müzik üretimi hakkında paylaşım yapıyor.",
            "posts": ["Yeni albüm kayıtları tamamlandı."],
        },
        "cognitive_friction": 0.8,
        "friction_profile": {
            "sensitivities": ["yargılanma korkusu"],
            "stress_triggers": ["aşırı dikkat çekme"],
        },
        "passion_profile": {
            "core_passions": ["özgünlük"],
            "energizing_topics": ["felsefe"],
        },
        "cognitive_style": {"communication_tone": "keskin"},
    }

    result = await agent.execute(payload)

    assert isinstance(result, LilithContentPackage)
    assert result.hook == "Çoğu insan başarısızlıktan değil, parlamaktan korkar."
    assert result.platform == "x_twitter"
    assert "https://image.pollinations.ai/prompt/" in result.pollinations_image_url
    assert result.image_generation_status == "request_url_created_unverified"
    assert result.data_confidence is True
    assert result.confidence == 0.95
    prompt = mock_gateway.chat.await_args.kwargs["messages"][0]["content"]
    assert "Kamuya açık müzik üretimi" in prompt
    assert "Yeni albüm kayıtları tamamlandı" in prompt
    assert result.neurochemical_profile is not None
    assert result.neurochemical_profile.dopamine_potential >= 0.05
    assert result.neuro_metrics is not None
    assert result.neuro_metrics == LilithGrowthAgent.compute_neuro_formula(
        dopamine=0.8, serotonin=0.7, cortisol=0.6, oxytocin=0.5,
        cognitive_friction=0.8,
    )
    assert "F=0.80" in result.formula_breakdown
    assert 0.0 <= result.neuro_metrics.viral_coefficient_score <= 10.0
    assert result.neuro_metrics.dominant_neurotransmitter in {
        "dopamine", "serotonin", "cortisol", "oxytocin"
    }


@pytest.mark.asyncio
async def test_lilith_growth_agent_fallback_resilience():
    """Gateway hatası boş ve açıkça fallback olarak işaretli kalmalıdır."""
    failing_gateway = MagicMock()
    failing_gateway.chat = AsyncMock(side_effect=RuntimeError("LLM Gateway down"))

    agent = LilithGrowthAgent(llm_gateway=failing_gateway)
    pkg = await agent.execute({"topic": "Statü Kaygısı"})

    assert isinstance(pkg, LilithContentPackage)
    assert pkg.confidence == 0.0
    assert pkg.data_confidence is False
    assert pkg.fallback_reason == "llm_unavailable"
    assert pkg.hook == pkg.content_body == pkg.call_to_action == ""
    assert pkg.pollinations_image_url == ""
    assert pkg.neurochemical_profile is None
    assert pkg.neuro_metrics is None


@pytest.mark.asyncio
async def test_lilith_growth_agent_partial_malformed_llm_fields_do_not_crash():
    """LLM'in tek bir alanı bozuk döndürmesi TÜM üretimi fallback'e düşürmemeli."""
    mock_gateway = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = """{
      "hook": "test hook",
      "psychological_angle": "test angle",
      "content_body": "test body",
      "call_to_action": "test cta",
      "pollinations_image_prompt": "test prompt",
      "dopamine": "çok yüksek",
      "cortisol": null,
      "confidence": "yüksek"
    }"""
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_gateway.chat = AsyncMock(return_value=mock_response)

    agent = LilithGrowthAgent(llm_gateway=mock_gateway)
    result = await agent.execute({"topic": "Test"})

    assert isinstance(result, LilithContentPackage)
    assert result.fallback_reason is None  # bozuk opsiyonel alanlar içeriği çökertmemeli
    assert result.hook == "test hook"
    assert result.confidence == 0.0  # geçersiz güven metni varsayılan güven üretmez
    assert result.data_confidence is False
    assert result.confidence_reason == "invalid_model_confidence"
    assert result.neuro_metrics is None  # eksik sayısal alanlar baseline uydurmaz


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_confidence", [1.01, float("nan"), True])
async def test_lilith_rejects_nonfinite_and_out_of_range_confidence(bad_confidence):
    content = json.dumps({
        "hook": "Hook",
        "psychological_angle": "Angle",
        "content_body": "Body",
        "call_to_action": "CTA",
        "confidence": bad_confidence,
    })
    gateway = MagicMock()
    gateway.chat = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    ))
    result = await LilithGrowthAgent(llm_gateway=gateway).execute({
        "target_profile": {"bio": "Sağlanan profil metni."}
    })
    assert result.confidence == 0.0
    assert result.data_confidence is False
    assert result.confidence_reason == "invalid_model_confidence"
    # Invalid confidence does not erase otherwise valid generated content.
    assert result.hook == "Hook"
    assert result.fallback_reason is None


@pytest.mark.asyncio
async def test_empty_json_is_not_a_successful_lilith_package():
    gateway = MagicMock()
    gateway.chat = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="{}"))]
    ))

    result = await LilithGrowthAgent(llm_gateway=gateway).execute({"topic": "Test"})

    assert result.fallback_reason == "invalid_model_response"
    assert result.confidence == 0.0
    assert result.data_confidence is False
    assert result.hook == result.content_body == ""


@pytest.mark.asyncio
async def test_default_gateway_contract_uses_structured_llm_chain():
    """LLMGateway-like objects use query_json_chain, not an undeclared .chat()."""
    class StructuredGateway:
        def __init__(self):
            self.kwargs = None

        async def query_json_chain(self, **kwargs):
            self.kwargs = kwargs
            return LilithGenerationResponse(
                hook="Hook",
                psychological_angle="Angle",
                content_body="Body",
                call_to_action="Question?",
                confidence=0.4,
            )

    gateway = StructuredGateway()
    result = await LilithGrowthAgent(llm_gateway=gateway).execute({"topic": "Test"})

    assert result.fallback_reason is None
    assert result.hook == "Hook"
    assert gateway.kwargs["schema"] is LilithGenerationResponse
    assert gateway.kwargs["agent_name"] == "lilith_growth"


def test_safe_float_handles_float_overflow_and_empty_image_prompt():
    from agent_core.agents.lilith_growth import _safe_float

    assert _safe_float(10**400, 0.25) == 0.25
    assert LilithGrowthAgent().build_pollinations_url("  ") == ""


# --------------------------------------------------------------------------- #
# $V_c$ Formülü — Matematiksel Sınır ve Uç-Durum Testleri
# --------------------------------------------------------------------------- #

class TestComputeNeuroFormulaEdgeCases:

    def test_default_values_produce_high_viral_score(self):
        metrics = LilithGrowthAgent.compute_neuro_formula(
            dopamine=0.95, serotonin=0.90, cortisol=0.70, oxytocin=0.60, cognitive_friction=0.20
        )
        assert metrics.viral_coefficient_score > 5.0
        assert metrics.dominant_neurotransmitter == "dopamine"
        assert "nucleus_accumbens" in metrics.target_brain_region

    def test_high_threat_profile_selects_amygdala(self):
        metrics = LilithGrowthAgent.compute_neuro_formula(
            dopamine=0.30, serotonin=0.40, cortisol=0.98, oxytocin=0.20, cognitive_friction=0.50
        )
        assert metrics.dominant_neurotransmitter == "cortisol"
        assert "amygdala" in metrics.target_brain_region

    def test_zero_and_negative_inputs_never_crash(self):
        metrics = LilithGrowthAgent.compute_neuro_formula(
            dopamine=0.0, serotonin=-5.0, cortisol=0.0, oxytocin=-1.0, cognitive_friction=0.0
        )
        assert isinstance(metrics, NeuroMetrics)
        assert 0.5 <= metrics.viral_coefficient_score <= 10.0
        assert 0.0 <= metrics.pattern_interrupt_index <= 1.0
        assert 0.0 <= metrics.cognitive_dissonance_score <= 1.0

    def test_zero_cognitive_friction_never_divides_by_zero(self):
        """cognitive_friction=0.0 -> ZeroDivisionError riski; floor=0.10 ile imkânsız kılınmalı."""
        metrics = LilithGrowthAgent.compute_neuro_formula(cognitive_friction=0.0)
        assert metrics.viral_coefficient_score > 0.0

    def test_nan_and_infinite_inputs_fall_back_to_safe_defaults(self):
        metrics = LilithGrowthAgent.compute_neuro_formula(
            dopamine=float("nan"),
            serotonin=float("inf"),
            cortisol=float("-inf"),
            oxytocin=float("nan"),
            cognitive_friction=float("nan"),
        )
        assert isinstance(metrics, NeuroMetrics)
        assert 0.5 <= metrics.viral_coefficient_score <= 10.0
        assert metrics.dominant_neurotransmitter in {"dopamine", "serotonin", "cortisol", "oxytocin"}

    def test_non_numeric_and_wrong_type_inputs_never_raise(self):
        metrics = LilithGrowthAgent.compute_neuro_formula(
            dopamine="çok yüksek",       # type: ignore[arg-type]
            serotonin=None,               # type: ignore[arg-type]
            cortisol="0.9",
            oxytocin=[1, 2, 3],           # type: ignore[arg-type]
            cognitive_friction="abc",
        )
        assert isinstance(metrics, NeuroMetrics)
        assert 0.5 <= metrics.viral_coefficient_score <= 10.0

    def test_extreme_upper_bound_inputs_are_clamped_to_ten(self):
        metrics = LilithGrowthAgent.compute_neuro_formula(
            dopamine=999.0, serotonin=999.0, cortisol=999.0, oxytocin=999.0,
            cognitive_friction=0.0001,
        )
        assert metrics.viral_coefficient_score <= 10.0

    def test_pydantic_validators_clamp_out_of_range_direct_construction(self):
        """compute_neuro_formula bypass edilip model doğrudan çağrılsa bile kenetleme çalışmalı."""
        chem = NeurochemicalProfile(
            dopamine_potential=5.0,
            serotonin_status_currency=-3.0,
            cortisol_urgency=float("nan"),
            oxytocin_affinity="bozuk",  # type: ignore[arg-type]
        )
        assert 0.0 <= chem.dopamine_potential <= 1.0
        assert 0.0 <= chem.serotonin_status_currency <= 1.0
        assert 0.0 <= chem.cortisol_urgency <= 1.0
        assert 0.0 <= chem.oxytocin_affinity <= 1.0

        metrics = NeuroMetrics(
            viral_coefficient_score=999.0,
            pattern_interrupt_index=-1.0,
            cognitive_dissonance_score=2.0,
            dominant_neurotransmitter="unknown_hormone",
        )
        assert 0.0 <= metrics.viral_coefficient_score <= 10.0
        assert 0.0 <= metrics.pattern_interrupt_index <= 1.0
        assert 0.0 <= metrics.cognitive_dissonance_score <= 1.0
        assert metrics.dominant_neurotransmitter == "dopamine"


# --------------------------------------------------------------------------- #
# Rapor Formatlama — Tek Kaynak Doğrulaması
# --------------------------------------------------------------------------- #

def test_render_console_report_contains_key_sections():
    pkg = LilithContentPackage(
        platform="x_twitter",
        hook="test hook",
        psychological_angle="test angle",
        content_body="test body",
        call_to_action="test cta",
        pollinations_image_prompt="test prompt",
        pollinations_image_url="https://image.pollinations.ai/prompt/test",
        neurochemical_profile=NeurochemicalProfile(),
        neuro_metrics=LilithGrowthAgent.compute_neuro_formula(),
    )
    report = LilithGrowthAgent.render_console_report(pkg)
    assert "BİLİŞSEL KANCA" in report
    assert "BİLEŞİK VİRAL KATSAYI" in report
    assert "test hook" in report
    assert "MODEL ÇIKTISI — BAĞIMSIZ OLARAK DOĞRULANMADI" in report
    assert "biyolojik/klinik ölçüm değildir" in report
    assert "ÜRETİM DOĞRULANMADI" in report


def test_render_console_report_marks_fallback_mode():
    pkg = LilithContentPackage(
        platform="x_twitter",
        hook="fallback hook",
        psychological_angle="-",
        content_body="-",
        call_to_action="-",
        pollinations_image_prompt="-",
        pollinations_image_url="https://image.pollinations.ai/prompt/x",
        fallback_reason="error: boom",
    )
    report = LilithGrowthAgent.render_console_report(pkg)
    assert "MODEL ÇAĞRISI BAŞARISIZ — FALLBACK" in report
    assert "FALLBACK NEDENİ" in report
    assert "model çıktısı yok" in report


# --------------------------------------------------------------------------- #
# CLI Gateway Adaptörleri (DRY Doğrulaması)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_free_text_gateway_strips_code_fences():
    gateway = FreeTextGateway()
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.text = '```json\n{"hook": "x"}\n```'

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        result = await gateway.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.choices[0].message.content == '{"hook": "x"}'


def test_from_cli_credentials_selects_correct_gateway():
    """[P3 · 2026-10-16] Varsayılan gateway **ana hattın** LLMGateway'idir.

    M-2 düzeltmesi: Lilith CLI artık kendi `httpx` adaptörünü kullanmaz;
    böylece NINEROUTER_*/canlı kapı/bütçe sayacı Lilith için de geçerlidir.
    Eski adaptör yalnızca AÇIKÇA seçildiğinde kullanılır.
    """
    from agent_core.services.llm_gateway import LLMGateway

    agent_with_key = LilithGrowthAgent.from_cli_credentials(
        api_key="sk-test", base_url=None, model="gpt-4o"
    )
    assert isinstance(agent_with_key.llm_gateway, LLMGateway)

    legacy_agent = LilithGrowthAgent.from_cli_credentials(
        api_key="sk-test", base_url=None, model="gpt-4o", use_main_line_gateway=False
    )
    assert isinstance(legacy_agent.llm_gateway, OpenAICompatibleGateway)

    agent_without_key = LilithGrowthAgent.from_cli_credentials(
        api_key=None, base_url=None, model="gpt-4o"
    )
    assert isinstance(agent_without_key.llm_gateway, FreeTextGateway)
