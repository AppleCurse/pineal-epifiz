import logging
import pytest
from unittest.mock import AsyncMock, MagicMock
from agent_core.agents.authenticity_auditor import AuthenticityAuditorAgent, AuthenticityProfile
from agent_core.services.llm_gateway import LLMGateway

# --- HERMETIC TEST GUARD: blocks live LLM calls ---
@pytest.fixture(autouse=True)
def _hermetic_guard(monkeypatch):
    async def _blocked(self, *a, **k):
        raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED: unit test kipi")
    monkeypatch.setattr(LLMGateway, "query", _blocked)
    monkeypatch.setattr(LLMGateway, "query_json", _blocked)


def test_uninitialized_authenticity_profile_does_not_claim_perfect_score():
    profile = AuthenticityProfile()
    assert profile.authenticity_score == 0.0
    assert profile.confidence == 0.0
    assert profile.data_confidence is False


@pytest.mark.asyncio
async def test_auditor_rejects_nonfinite_model_scores():
    returned = AuthenticityProfile(
        authenticity_score=0.8,
        supported_claims=["beğeni alanı"],
        confidence=0.8,
    ).model_copy(update={"confidence": float("nan")})
    gateway = MagicMock(spec=LLMGateway)
    gateway.query_json_chain = AsyncMock(return_value=returned)
    agent = AuthenticityAuditorAgent(gateway)
    result = await agent.execute({
        "target_profile": {"bio": "Yazar"},
        "visual_evidence": {"detected_objects": ["kitap"]},
    })
    assert result.confidence == 0.0
    assert result.authenticity_score == 0.0
    assert result.data_confidence is False
    assert result.fallback_reason == "invalid_model_score"


@pytest.mark.asyncio
async def test_auditor_empty_visual_evidence_early_return():
    """Görsel kanıt olmadığında analiz yapılmadan confidence=0 ile erken dönülmelidir."""
    agent = AuthenticityAuditorAgent()
    payload = {
        "target_profile": {"bio": "Doğa tutkunu", "posts": ["orman gezisi"]},
        "visual_evidence": {}
    }
    res = await agent.execute(payload)
    assert isinstance(res, AuthenticityProfile)
    assert res.confidence == 0.0
    assert res.authenticity_score == 0.0
    assert res.visual_text_gaps == []
    assert res.supported_claims == []
    assert res.data_confidence is False
    assert res.fallback_reason == "insufficient_evidence"


@pytest.mark.asyncio
async def test_auditor_empty_bio_and_posts_early_return():
    """Metinsel beyan (bio ve posts) olmadığında confidence=0 ile erken dönülmelidir."""
    agent = AuthenticityAuditorAgent()
    payload = {
        "target_profile": {"bio": "", "posts": []},
        "visual_evidence": {"detected_objects": ["kitap", "kahve"]}
    }
    res = await agent.execute(payload)
    assert isinstance(res, AuthenticityProfile)
    assert res.confidence == 0.0
    assert res.authenticity_score == 0.0
    assert res.data_confidence is False
    assert res.fallback_reason == "insufficient_evidence"


@pytest.mark.asyncio
async def test_auditor_normal_path_calls_llm_chain():
    """Görsel ve metinsel kanıtlar mevcutken LLM zinciri çağrılmalı ve sonuç dönmelidir."""
    mock_gateway = MagicMock(spec=LLMGateway)
    expected_profile = AuthenticityProfile(
        authenticity_score=0.88,
        visual_text_gaps=["Minimalist bio beyanına karşın fotoğraflarda lüks eşyalar mevcut."],
        supported_claims=["Kitap okuma ve analog fotoğrafçılık hobisi görsellerle doğrulanmıştır."],
        confidence=0.92
    )
    mock_gateway.query_json_chain = AsyncMock(return_value=expected_profile)
    
    agent = AuthenticityAuditorAgent(llm_gateway=mock_gateway)
    payload = {
        "target_profile": {
            "bio": "Minimalist yazar, analog kamera sevdalısı.",
            "posts": ["Yeni yazım için inzivadayım.", "Analog çekimler bambaşka."]
        },
        "visual_evidence": {
            "detected_objects": ["Leica M6 analog kamera", "kodak film ruloları", "daktilo"],
            "environment_and_places": ["ahşap çalışma masası", "kütüphane"],
            "activity_signals": ["film sarma", "yazı yazma"],
            "aesthetic_style": "vintage analog"
        }
    }
    
    res = await agent.execute(payload)
    assert isinstance(res, AuthenticityProfile)
    assert res.authenticity_score == 0.88
    assert res.confidence == 0.92
    assert res.data_confidence is True
    assert res.fallback_reason is None
    assert len(res.supported_claims) == 1
    
    mock_gateway.query_json_chain.assert_awaited_once()
    call_kwargs = mock_gateway.query_json_chain.call_args.kwargs
    assert call_kwargs["task"] == "depth"
    assert call_kwargs["schema"] == AuthenticityProfile
    assert call_kwargs["temperature"] == 0.2


@pytest.mark.asyncio
async def test_auditor_llm_exception_fallback_and_logging(caplog):
    """LLM hatasında confidence=0.2 fallback dönmeli ve logger.warning istisnayı kaydetmelidir."""
    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.query_json_chain = AsyncMock(side_effect=RuntimeError("Gateway timeout error"))
    
    agent = AuthenticityAuditorAgent(llm_gateway=mock_gateway)
    payload = {
        "target_profile": {"bio": "Gezgin", "posts": ["Seyahat"]},
        "visual_evidence": {"detected_objects": ["bavul"]}
    }
    
    with caplog.at_level(logging.WARNING):
        res = await agent.execute(payload)
    
    assert isinstance(res, AuthenticityProfile)
    assert res.confidence == 0.0
    assert res.authenticity_score == 0.0
    assert res.visual_text_gaps == []
    assert res.data_confidence is False
    assert res.fallback_reason == "llm_unavailable"
    
    # logger.warning çağrısının hata metnini içerdiğini doğrula
    assert any("AuthenticityAuditor LLM hatası: Gateway timeout error" in record.message for record in caplog.records)
