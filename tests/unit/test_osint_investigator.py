import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent_core.agents.osint_investigator import OsintInvestigatorAgent, OsintProfile
from agent_core.services.llm_gateway import LLMGateway

# --- HERMETIC TEST GUARD: blocks live LLM calls ---
@pytest.fixture(autouse=True)
def _hermetic_guard(monkeypatch):
    async def _blocked(self, *a, **k):
        raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED: unit test kipi")
    monkeypatch.setattr(LLMGateway, "query", _blocked)
    monkeypatch.setattr(LLMGateway, "query_json", _blocked)


def test_uninitialized_osint_profile_does_not_claim_data_or_confidence():
    profile = OsintProfile()
    assert profile.confidence == 0.0
    assert profile.data_confidence is False
    assert profile.fallback_reason == "unavailable"


@pytest.mark.asyncio
async def test_osint_empty_username():
    """Kullanıcı adı yoksa veri yokluğu açıkça belirtilmelidir."""
    agent = OsintInvestigatorAgent()
    payload = {"target_profile": {"username": "", "bio": "Bir gezgin"}}
    res = await agent.execute(payload)
    assert isinstance(res, OsintProfile)
    assert res.confidence == 0.0
    assert res.error_code == "NO_TARGET_IDENTITY"
    assert res.connected_emails == []
    assert res.associated_platforms == []


@pytest.mark.asyncio
async def test_osint_no_api_key_skips_llm_and_returns_dry_fallback(monkeypatch):
    """API anahtarı yoksa OSINT uydurma profil üretmeden boş fallback döndürür."""
    monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)
    
    mock_gateway = MagicMock(spec=LLMGateway)
    expected_profile = OsintProfile(
        connected_emails=["tahmini_maskelenmis@gmail.com"],
        connected_phones=[],
        associated_platforms=["GitHub", "Spotify", "LinkedIn"],
        digital_footprint_score=0.75,
        dark_web_hits=0,
        confidence=0.85
    )
    mock_gateway.query_json_chain = AsyncMock(return_value=expected_profile)
    
    agent = OsintInvestigatorAgent(llm_gateway=mock_gateway)
    payload = {
        "target_profile": {
            "username": "@tech_wanderer",
            "bio": "Open source coder, loves acoustic music and photography."
        }
    }
    
    res = await agent.execute(payload)
    assert isinstance(res, OsintProfile)
    assert res.connected_emails == []
    assert res.connected_phones == []
    assert res.associated_platforms == []
    assert res.dark_web_hits == 0
    assert res.digital_footprint_score == 0.0
    assert res.confidence == 0.0
    assert res.data_confidence is False
    assert res.fallback_reason == "provider_credentials_unavailable"
    mock_gateway.query_json_chain.assert_not_awaited()
    


@pytest.mark.asyncio
async def test_osint_llm_failure_graceful_fallback(monkeypatch):
    """LLM sorgusu yerine dönmeyen hatada güven sıfırlanmalıdır."""
    monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)
    
    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.query_json_chain = AsyncMock(side_effect=RuntimeError("Rate limit / OpenRouter down"))
    
    agent = OsintInvestigatorAgent(llm_gateway=mock_gateway)
    payload = {"target_profile": {"username": "test_target", "bio": "bio text"}}
    
    res = await agent.execute(payload)
    assert isinstance(res, OsintProfile)
    assert res.confidence == 0.0
    assert res.associated_platforms == []


@pytest.mark.asyncio
@patch("aiohttp.ClientSession.get")
async def test_osint_with_api_key_simulation(mock_get, monkeypatch):
    """OSINT_INDUSTRIES_KEY mevcutken canlı bağlantı simülasyonu çalışmalıdır."""
    monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")

    # Configure the mock
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        "emails": ["test@example.com"],
        "phones": [],
        "platforms": ["X"]
    })

    # Set __aenter__ to return the mock response object
    mock_get.return_value.__aenter__.return_value = mock_resp

    agent = OsintInvestigatorAgent()
    payload = {"target_profile": {"username": "cyber_agent"}}
    
    res = await agent.execute(payload)
    assert isinstance(res, OsintProfile)
    assert res.confidence == round(2 / 3, 3)
    assert res.data_confidence is True
    assert res.fallback_reason is None
    assert res.connected_emails == ["test@example.com"]
    assert res.associated_platforms == ["X"]
