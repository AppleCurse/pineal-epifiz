"""[009]/[015]/[028]/[014] regression: kullanıcı verisi uydurma + verifier
kanıt sözleşmesi + mirror ölçülmemiş alignment.

- Boş rituals/playlist/envies -> boş listeler; sahte örnek ÜRETİLMEZ.
- Verifier: provider key yoksa UNVERIFIED + confidence 0.0 +
  data_confidence=False + fallback_reason (DDG verifier yolunda kapalı).
- Mirror LLM fallback: alignment_score ölçülmediyse 0.0 (0.5 üretilmez),
  data_confidence=False.
"""
from unittest.mock import MagicMock, patch

import pytest

from agent_core.agents.autonomous_verifier import AutonomousVerifier
from agent_core.agents.mirror_truth import MirrorOfTruth
from backend.api import InitiatePayload, run_mission


# ------------------------------------------------------------------ #
# [009] default rituals
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_empty_user_fields_never_reach_executor_as_placeholders():
    captured = {}

    async def fake_execute(payload, task_id):
        captured["user_profile"] = payload.get("user_profile", {})
        captured["user_context"] = payload.get("user_context", {})
        return MagicMock(status="completed")

    executor = MagicMock()
    executor.execute_task = fake_execute

    with patch("backend.api.get_room", return_value={}), \
         patch("backend.api.get_vault", return_value=MagicMock(get=MagicMock(return_value=""))), \
         patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.broadcast_log"), \
         patch("backend.api.broadcast_result"):
        await run_mission(InitiatePayload(
            client_id="fx_empty_user",
            url="",
            rituals="",
            playlist="",
            envies="",
            aggressiveness=1.0,
            evidence_th=3,
            scraper_type="instagram",
        ))

    assert captured["user_profile"]["private_rituals"] == []
    assert captured["user_profile"]["late_night_playlist"] == []
    assert captured["user_profile"]["secret_envies"] == []
    assert captured["user_context"]["rituals"] == ""
    assert captured["user_context"]["playlist"] == ""
    assert captured["user_context"]["envies"] == ""
    # Sahte örnek listeler asla payload'a girmedi
    assert "Gece stüdyo kayıtları" not in str(captured)
    assert "Dark Jazz" not in str(captured)
    assert "Sahici ve derin diyalog" not in str(captured)


@pytest.mark.asyncio
async def test_provided_user_fields_still_pass_through():
    captured = {}

    async def fake_execute(payload, task_id):
        captured["user_profile"] = payload.get("user_profile", {})
        return MagicMock(status="completed")

    executor = MagicMock()
    executor.execute_task = fake_execute

    with patch("backend.api.get_room", return_value={}), \
         patch("backend.api.get_vault", return_value=MagicMock(get=MagicMock(return_value=""))), \
         patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.broadcast_log"), \
         patch("backend.api.broadcast_result"):
        await run_mission(InitiatePayload(
            client_id="fx_user_ok",
            url="",
            rituals="çay, kitap",
            playlist="neşet ertaş",
            envies="derin bağ",
            aggressiveness=1.0,
            evidence_th=3,
            scraper_type="instagram",
        ))

    assert captured["user_profile"]["private_rituals"] == ["çay", "kitap"]
    assert captured["user_profile"]["late_night_playlist"] == ["neşet ertaş"]
    assert captured["user_profile"]["secret_envies"] == ["derin bağ"]


# ------------------------------------------------------------------ #
# [015]+[028] verifier provider gating
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_verifier_no_provider_key_is_unverified_with_reason():
    mock_search = MagicMock()
    mock_search.tavily_key = None
    mock_search.serpapi_key = None
    mock_search.exa_key = None

    verifier = AutonomousVerifier(search_engine=mock_search)
    report = await verifier.execute(
        {"target_profile": {"bio": "Eski bir startup kurucusu"}},
        memory=None,
        llm_gateway=None,
    )

    assert report.status == "UNVERIFIED"
    assert report.confidence == 0.0
    assert report.data_confidence is False
    assert report.fallback_reason == "no_search_provider"


@pytest.mark.asyncio
async def test_verifier_any_provider_key_is_enough_for_claims():
    """SerpAPI/Exa anahtarı da verifier sözleşmesini karşılar."""
    mock_search = MagicMock()
    mock_search.tavily_key = None
    mock_search.serpapi_key = "serp-key"
    mock_search.exa_key = None

    verifier = AutonomousVerifier(search_engine=mock_search)
    report = await verifier.execute(
        {"target_profile": {"bio": "Eski bir startup kurucusu"}},
        memory=None,
        llm_gateway=None,
    )

    # provider kapısından geçti; LLM yok -> claim çıkarılamadı -> no_claims
    assert report.status == "UNVERIFIED"
    assert report.confidence == 0.0
    assert report.data_confidence is False
    assert report.fallback_reason == "no_claims"


@pytest.mark.asyncio
async def test_verifier_no_bio_reason_is_no_bio():
    mock_search = MagicMock()
    mock_search.tavily_key = None
    verifier = AutonomousVerifier(search_engine=mock_search)
    report = await verifier.execute(
        {"target_profile": {}}, memory=None, llm_gateway=None
    )
    assert report.fallback_reason == "no_bio"
    assert report.data_confidence is False
    assert report.confidence == 0.0


# ------------------------------------------------------------------ #
# [014] mirror fallback alignment
# ------------------------------------------------------------------ #
class _FailingGateway:
    async def query_json(self, *args, **kwargs):
        raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED: test")


@pytest.mark.asyncio
async def test_mirror_llm_fallback_never_measures_alignment_half():
    mirror = MirrorOfTruth(_FailingGateway())
    result = await mirror.execute({
        "user_profile": {
            "private_rituals": ["kahve"],
            "late_night_playlist": "klasik",
            "secret_envies": "bağ",
        },
    })

    assert result.data_confidence is False
    assert result.fallback_reason == "llm_unavailable"
    assert result.confidence == 0.0
    # Ölçülmemiş uyum "nötr orta" (0.5) gösterilemez
    assert result.alignment_score == 0.0
