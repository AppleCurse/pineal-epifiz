"""[019] ShadowExecutor kanıt kapısı: boş hedefte sahte shadow profili üretilmez.

Kural: hedef bio/posts/username/name/images yoksa strateji, mesaj ve NLP
dizisi ÜRETİLEMEZ; sonuç data_confidence=False + confidence=0.0 olarak
kaydedilir ve DecisionEngine onu kanıt saymaz.
"""
import pytest

from agent_core.config_loader import DecisionConfig
from agent_core.domain.memory_models import AgentRun
from agent_core.domain.pipeline_status import PipelineStatus
from agent_core.services.decision_engine import DecisionEngine
from agent_core.shadow.shadow_executor import ShadowExecutor


@pytest.mark.asyncio
async def test_shadow_empty_target_produces_no_fabricated_profile():
    executor = ShadowExecutor()
    result = await executor.execute({"target_profile": {}, "user_profile": {}})

    assert result.data_confidence is False
    assert result.confidence == 0.0
    assert result.fallback_reason == "target_evidence_unavailable"
    assert result.strategy == "unavailable"
    assert result.message == ""
    assert result.nlp_sequence == []


@pytest.mark.asyncio
async def test_shadow_with_lexical_input_only_produces_no_strategy():
    """GÖREV 2.1: kelime-yuku trait gozlemi DEGILDIR; strateji uretilmez."""
    executor = ShadowExecutor()
    result = await executor.execute({
        "target_profile": {
            "bio": "Mükemmel, mükemmel, mükemmel, mükemmel, eşsiz, eşsiz, olağanüstü, benzersiz, seçilmiş. Mükemmeliyetçi ve hırslı bir lider.",
            "posts": ["Başarı tek seçenektir.", "Kontrol bende."],
        },
        "user_profile": {"rituals": ["kahve"], "music": "klasik", "envies": "derin bağ"},
        "target_beliefs": ["kontrolü elde tutmak"],
    })
    assert result.data_confidence is False
    assert result.message == ""
    assert result.strategy == "unavailable"
    assert result.fallback_reason == "dark_triad_markers_unobserved"


async def test_shadow_does_not_regenerate_a_claim_gate_blocked_routed_message(monkeypatch):
    from unittest.mock import AsyncMock
    from agent_core.psychology.dark_triad import DarkTriadProfile

    executor = ShadowExecutor()
    monkeypatch.setattr(
        executor.dark_triad, "analyze",
        lambda profile_data: DarkTriadProfile(narcissism=0.8),
    )
    executor.mirror.execute = AsyncMock()
    executor.pattern.execute = AsyncMock()
    result = await executor.execute({
        "target_profile": {"bio": "A real target profile"},
        "_pattern_interrupt": {
            "message": "",
            "claim_gate_blocked_ids": ["clm_0123456789abcdefabcd"],
        },
    })

    assert result.message == ""
    assert result.data_confidence is False
    assert result.fallback_reason == "claim_gate_blocked_same_claim"
    executor.pattern.execute.assert_not_awaited()
    executor.mirror.execute.assert_not_awaited()


async def test_shadow_with_observed_traits_still_synthesizes(monkeypatch):
    """GÖREV 2.1 sonrasi yetenek kilidi: gozlem verilirse sentez uretir."""
    from agent_core.psychology.dark_triad import DarkTriadProfile
    executor = ShadowExecutor()
    monkeypatch.setattr(
        executor.dark_triad, "analyze",
        lambda profile_data: DarkTriadProfile(narcissism=0.8),
    )
    result = await executor.execute({
        "target_profile": {
            "bio": "Mükemmel, mükemmel, mükemmel, mükemmel, eşsiz, eşsiz, olağanüstü, benzersiz, seçilmiş. Mükemmeliyetçi ve hırslı bir lider.",
            "posts": ["Başarı tek seçenektir.", "Kontrol bende."],
        },
        "user_profile": {"rituals": ["kahve"], "music": "klasik", "envies": "derin bağ"},
        "target_beliefs": ["kontrolü elde tutmak"],
    })
    assert result.data_confidence is True
    assert isinstance(result.message, str) and len(result.message) > 0
    assert result.strategy == "mirroring"
    assert len(result.nlp_sequence) == 3


def test_unavailable_shadow_run_is_not_pipeline_evidence():
    """data_confidence=False + target_evidence_unavailable shadow kaydı
    'completed' görünse bile kanıt sayılmaz."""
    config = DecisionConfig.load()
    result = DecisionEngine(config).make_decision({
        "shadow_executor": AgentRun(
            task_id="x", agent_name="shadow_executor", status="completed",
            confidence=None,
            warnings=["target_evidence_unavailable"],
            output_summary={
                "message": "",
                "strategy": "unavailable",
                "nlp_sequence": [],
                "dark_profile": {"machiavellianism": 0.0, "exploitability": 0.0},
                "data_confidence": False,
            },
        ),
        "osint_investigator": AgentRun(
            task_id="y", agent_name="osint_investigator", status="completed",
            confidence=None,
            warnings=["no_target_identity"],
            output_summary={
                "associated_platforms": [],
                "digital_footprint_score": 0.0,
                "data_confidence": False,
            },
        ),
    })
    assert result == PipelineStatus.HALTED_INSUFFICIENT_EVIDENCE
