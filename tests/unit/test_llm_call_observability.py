"""Gözlemlenebilirlik: LLM çağrı metadata'sı evidence chain'e yazılır.

Kurallar:
- Gate kapalıyken query() REDDEDİLİR ve call_log'a error kaydı düşer
  (hangi model, kaç deneme, hangi hata).
- Ajan çalıştığı sırada gateway üzerinden yapılan her deneme, o ajanın
  evidence kaydındaki llm_calls listesinde görünür (sahte değil).
- Cache'ten gelen yanıt da provider="cache" olarak işaretlenir.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_core.domain.memory_models import CognitiveStyle
from agent_core.services.llm_gateway import LLMGateway
from agent_core.task_executor import PinealExecutor


class RouteOne:
    agents = ["cognitive_profiler"]


@pytest.mark.asyncio
async def test_blocked_query_is_logged_with_error():
    import os
    os.environ.pop("LIVE_LLM_E2E", None)
    gateway = LLMGateway()
    gateway.call_log.clear()
    with pytest.raises(RuntimeError) as exc_info:
        await gateway.query("test prompt")
    assert "REAL_LLM_CALL_NOT_EXECUTED" in str(exc_info.value)
    assert len(gateway.call_log) == 1
    entry = gateway.call_log[0]
    assert entry["kind"] == "query"
    assert entry["provider"] == "openrouter"
    assert entry["error"] == "REAL_LLM_CALL_NOT_EXECUTED"
    assert "model" in entry and "at" in entry


@pytest.mark.asyncio
async def test_executor_evidence_records_agent_llm_calls():
    """Ajan çalışırken yapılan (bloklu) deneme, evidence kaydında görünür."""
    executor = PinealExecutor()
    executor.router.analyze = AsyncMock(return_value=RouteOne())
    executor.memory = MagicMock()
    executor.memory.merge_evidence = AsyncMock()
    executor.injector.fetch_active_rules = MagicMock(return_value={})
    executor.llm_gateway.call_log.clear()

    real_gateway = executor.llm_gateway

    async def fake_execute(input_data, memory, llm_gateway):
        # Ajan gerçekten gateway'i kullanıyor; kapı kapalı -> hata loglanır
        try:
            await llm_gateway.query("agent prompt")
        except RuntimeError:
            pass  # beklenen: kapı kapalı -> RuntimeError; test bunu doğrular
        return CognitiveStyle(
            communication_tone="analitik",
            complexity_level="teknik",
            humor_style="kuru mizah",
            social_orientation="gözlemci",
            confidence=0.9,
            data_confidence=True,
        )

    executor.agents["cognitive_profiler"].execute = fake_execute

    status = await executor.execute_task(
        {"target_profile": {"bio": "test", "posts": ["x"]}},
        "llm_obs_1",
    )

    record = next(
        r for r in status.evidence_chain
        if r["agent"] == "cognitive_profiler"
    )
    assert "llm_calls" in record, "evidence kaydı llm_calls taşımalı"
    assert len(record["llm_calls"]) == 1
    entry = record["llm_calls"][0]
    assert entry["provider"] == "openrouter"
    assert entry["error"] == "REAL_LLM_CALL_NOT_EXECUTED"


@pytest.mark.asyncio
async def test_gateway_cache_hit_is_logged():
    """Cache'ten dönen yanıt provider='cache' olarak kaydedilir."""
    gateway = LLMGateway()
    gateway.call_log.clear()
    # Cache anahtarı canlı kapıdan SONRA bakılır; kapıyı açıyoruz ki
    # cache servis edilsin (client async çağrısına hiç girilmez).
    gateway.live_unlocked = True
    gateway.client = MagicMock()  # cache hit'te kullanılmaz
    gateway.cache = MagicMock()
    gateway.cache.is_cachable = MagicMock(return_value=True)
    gateway.cache.make_key = MagicMock(return_value="k1")
    gateway.cache.get = MagicMock(return_value="cached-answer")
    result = await gateway.query("prompt", model="x/y")
    assert result == "cached-answer"
    assert gateway.call_log[-1]["provider"] == "cache"
    assert gateway.call_log[-1]["cache_hit"] is True
    assert gateway.call_log[-1]["model"] == "x/y"
