"""Dalga 3.5: LLM Gateway maliyet dürüstlüğü + retry sınıflandırması.

[017] bilinmeyen fiyatlı modelde ÜCRETLİ canlı çağrı varsayılan olarak reddedilir
     (spend cap bypass edilemez); PINEAL_ALLOW_UNPRICED_MODELS=1 ile açık kabul +
     unpriced_calls sayacı; cache hit muaf (ücretsizdir).
[018] non-retryable hata sınıfları (400/403/404/422, model yok, bağlam limiti)
     retry EDİLMEZ; retryable sınıflar (429/5xx/timeout/bağlantı) retry edilir.
"""

import asyncio

import httpx
import pytest
from openai import AsyncOpenAI
from unittest.mock import AsyncMock

from agent_core.services.llm_gateway import LLMGateway, SpendCapExceeded


def _gateway_with_mock(handler, monkeypatch) -> LLMGateway:
    """Gerçek AsyncOpenAI istemcisi + sahte HTTP (test illüzyonu yok)."""
    monkeypatch.setenv("LIVE_LLM_E2E", "1")
    monkeypatch.delenv("USE_LOCAL_LLM", raising=False)
    monkeypatch.delenv("PINEAL_ALLOW_UNPRICED_MODELS", raising=False)
    gw = LLMGateway()
    gw.set_key("sk-or-v1-test", unlock_live=True)
    gw.client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-v1-test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return gw


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


# ------------------------------------------------------------------ #
# [017] bilinmeyen fiyat guard'ı
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_unpriced_model_paid_call_is_blocked_by_default(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok("asla dönmemeli")

    gw = _gateway_with_mock(handler, monkeypatch)
    with pytest.raises(RuntimeError, match="UNKNOWN_PRICING"):
        await gw.query("ping", model="unknown/model-x")
    assert calls["n"] == 0, "ücretli HTTP çağrısı hiç yapılmamalı"
    assert any(e.get("error") == "UNKNOWN_PRICING" for e in gw.call_log)


@pytest.mark.asyncio
async def test_unpriced_model_allowed_explicitly_and_counted(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok("takipsiz ama bilinçli")

    gw = _gateway_with_mock(handler, monkeypatch)
    # helper temizliyor; açık kabul bayrağını SONRA kur
    monkeypatch.setenv("PINEAL_ALLOW_UNPRICED_MODELS", "1")
    res = await gw.query("ping", model="unknown/model-x")
    assert res == "takipsiz ama bilinçli"
    assert calls["n"] == 1
    assert gw.unpriced_calls == 1
    # harcama hâlâ 0: takipsiz çağrı cap'e katkı YAPMAZ (kanıt: sayaç ayrı)
    assert gw.spend_usd == 0.0


@pytest.mark.asyncio
async def test_priced_model_still_accounts_spend(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
        })

    gw = _gateway_with_mock(handler, monkeypatch)
    await gw.query("ping", model="upstage/solar-pro4")
    # [2026-10-14] Fiyat BURAYA gömülmez: beklenen değer tablodan türetilir.
    # Gömülü $0.03, tablo canlı ölçümle $0.09'a güncellenince bu testi
    # kırmıştı — test maliyet MEKANİZMASINI sınar, fiyat sabitini değil.
    rate_in = LLMGateway.MODEL_PRICING["upstage/solar-pro4"]["in"]
    assert gw.spend_usd == pytest.approx(rate_in)  # 1M girdi token * tablo fiyatı


@pytest.mark.asyncio
async def test_cache_hit_serves_unpriced_model_without_guard(monkeypatch):
    """Cache hit ücretsizdir: fiyat guard'ı HTTP çağrısından önce değil,
    çağrı kararından önce uygulanır — cache'ten servis engellenmez."""
    monkeypatch.setenv("PINEAL_RESPONSE_CACHE", "1")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _ok("cache'lenecek")

    gw = _gateway_with_mock(handler, monkeypatch)
    # 1) fiyatlı modelle doldur
    await gw.query("aynı prompt", model="upstage/solar-pro4")
    assert calls["n"] == 1
    # 2) fiyatı bilinmeyen model + AYNI anahtar -> fiyat farkı cache'te ayrı
    #    olduğu için guard devrede; ama cache hit senaryosunda (1'deki model)
    #    ikinci çağrı HTTP'ye gitmez:
    await gw.query("aynı prompt", model="upstage/solar-pro4")
    assert calls["n"] == 1, "ikinci çağrı cache'ten gelmeli"


# ------------------------------------------------------------------ #
# [018] retry sınıflandırması
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_bad_request_400_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "invalid_request_error"}})

    gw = _gateway_with_mock(handler, monkeypatch)
    with pytest.raises(Exception):
        await gw.query("ping")
    assert calls["n"] == 1, "[018] 400 retry edilmemeli (eski davranış 3 kez deniyordu)"
    assert any("NON_RETRYABLE" in (e.get("error") or "") for e in gw.call_log)


@pytest.mark.asyncio
async def test_model_not_found_404_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"error": {"message": "model_not_found: yok"}})

    gw = _gateway_with_mock(handler, monkeypatch)
    with pytest.raises(Exception):
        # fiyatı BİLİNEN model + provider 404 (model kaydı silinmiş senaryosu)
        await gw.query("ping", model="upstage/solar-pro4")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_rate_limit_429_still_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return _ok("ikinci denemede")

    # backoff'u bekleme: test süresi şişmesin
    async def _no_sleep(delay):
        return None
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    gw = _gateway_with_mock(handler, monkeypatch)
    res = await gw.query("ping")
    assert res == "ikinci denemede"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_5xx_still_retries(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(503, json={"error": {"message": "geçici"}})
        return _ok("üçüncüde")

    async def _no_sleep(delay):
        return None
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    gw = _gateway_with_mock(handler, monkeypatch)
    res = await gw.query("ping")
    assert res == "üçüncüde"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_spend_cap_never_retries(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "0.001")
    create = AsyncMock(side_effect=AssertionError("cap aşılıyken HTTP çağrısı gitmemeli"))

    monkeypatch.setenv("LIVE_LLM_E2E", "1")
    gw = LLMGateway()
    gw.set_key("sk-test", unlock_live=True)
    gw.cache = None
    gw.spend_usd = 1.0  # cap zaten aşılmış
    gw.client = type("C", (), {"chat": type("CH", (), {"completions": type("Co", (), {"create": create})()})()})()

    with pytest.raises(SpendCapExceeded):
        await gw.query("ping", model="upstage/solar-pro4")
    create.assert_not_awaited()
