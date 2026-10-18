"""P0 regression coverage for atomic concurrent spend reservations."""

import asyncio

import pytest

from agent_core.services.llm_gateway import LLMGateway, SpendCapExceeded


# ── FİYATLAR TEK KAYNAKTAN TÜRETİLİR ────────────────────────────────────────
# Bu dosya rezervasyon/atomiklik MEKANİZMASINI sınar, fiyat sabitlerini değil.
# 2026-10-14'te solar-pro4'nun fiyatı canlı ölçümle $0.03/$0.12 -> $0.09/$0.36
# olunca, buraya gömülü cap ve maliyet sayıları testleri kırmıştı. Artık her
# beklenen değer MODEL_PRICING'ten hesaplanır: fiyat değişince yalnız tablo
# güncellenir, mekanizma testleri kendiliğinden doğru kalır.
_RATES = LLMGateway.MODEL_PRICING["upstage/solar-pro4"]
_PROMPT_TOKENS = len(b"prompt") + 64   # _estimate_input_cost: bayt + 64 çerçeve
_MAX_OUTPUT_TOKENS = 1000              # OPENROUTER_MAX_OUTPUT_TOKENS
_RESERVATION = (
    _PROMPT_TOKENS * _RATES["in"] + _MAX_OUTPUT_TOKENS * _RATES["out"]
) / 1_000_000.0
_OBSERVED_COST = (1_000 * _RATES["in"] + 500 * _RATES["out"]) / 1_000_000.0


def _cap(multiple: float) -> str:
    """n× rezervasyon: tam olarak n eşzamanlı çağrı sığar (semantik korunur)."""
    return f"{_RESERVATION * multiple:.9f}"


class _Usage:
    prompt_tokens = 1_000
    completion_tokens = 500


class _Response:
    usage = _Usage()
    choices = [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()]


class _SlowCompletions:
    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.03)
        return _Response()


class _BadRequestError(ValueError):
    status_code = 400


class _FailingCompletions:
    async def create(self, **kwargs):
        raise _BadRequestError("400 invalid request")


class _MalformedThenValidCompletions:
    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return type("MalformedResponse", (), {"usage": _Usage(), "choices": []})()
        return _Response()


class _BlockingCompletions:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def create(self, **kwargs):
        self.started.set()
        await self.release.wait()
        return _Response()


class _Client:
    def __init__(self, completions):
        self.chat = type("Chat", (), {"completions": completions})()


def _paid_gateway(monkeypatch, completions, *, cap: str | None = None) -> LLMGateway:
    monkeypatch.setenv("LIVE_LLM_E2E", "1")
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", cap if cap is not None else _cap(2.5))
    monkeypatch.setenv("OPENROUTER_MAX_OUTPUT_TOKENS", "1000")
    monkeypatch.delenv("USE_LOCAL_LLM", raising=False)
    gateway = LLMGateway()
    gateway.client = _Client(completions)
    gateway.cache = None
    return gateway


@pytest.mark.asyncio
@pytest.mark.parametrize("parallelism", [10, 50, 100])
async def test_concurrent_reservations_never_overbook_cap(monkeypatch, parallelism):
    completions = _SlowCompletions()
    gateway = _paid_gateway(monkeypatch, completions)

    async def invoke(index: int):
        with gateway.capture_calls("task-spend", f"agent-{index}"):
            try:
                return await gateway.query("prompt", model="upstage/solar-pro4")
            except SpendCapExceeded:
                return "rejected"

    results = await asyncio.gather(*(invoke(index) for index in range(parallelism)))

    # Rezervasyon çağrı başına _RESERVATION; cap 2,5× olduğu için en fazla İKİ
    # eşzamanlı çağrı sığar (3. rezervasyon cap'i aşar). Gözlenen toplam
    # 2 × _OBSERVED_COST.
    assert results.count("ok") == 2
    assert results.count("rejected") == parallelism - 2
    assert completions.calls == 2
    assert gateway.spend_usd <= gateway.spend_cap_usd
    assert gateway._reserved_spend_usd == pytest.approx(0.0)
    assert gateway._budget_reservations == {}

    rejected = [record for record in gateway.call_log if record["error"]]
    assert len(rejected) == parallelism - 2
    assert {record["error"] for record in rejected} == {"OPENROUTER_SPEND_CAP_EXCEEDED"}
    assert all(record["task_id"] == "task-spend" for record in gateway.call_log)
    assert len({record["call_id"] for record in gateway.call_log}) == parallelism


@pytest.mark.asyncio
async def test_failed_call_releases_reservation(monkeypatch):
    gateway = _paid_gateway(monkeypatch, _FailingCompletions(), cap=_cap(1.5))

    with pytest.raises(ValueError, match="400"):
        await gateway.query("prompt", model="upstage/solar-pro4")

    assert gateway.spend_usd == 0.0
    assert gateway._reserved_spend_usd == 0.0
    assert gateway._budget_reservations == {}

    gateway.client = _Client(_SlowCompletions())
    assert await gateway.query("prompt", model="upstage/solar-pro4") == "ok"
    assert gateway.spend_usd <= gateway.spend_cap_usd


@pytest.mark.asyncio
async def test_malformed_paid_response_is_settled_before_bounded_retry(monkeypatch):
    async def no_wait(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    completions = _MalformedThenValidCompletions()
    gateway = _paid_gateway(monkeypatch, completions, cap=_cap(2.5))
    gateway._is_retryable_error = lambda _exc: True

    assert await gateway.query("prompt", model="upstage/solar-pro4") == "ok"

    assert completions.calls == 2
    assert gateway.spend_usd == pytest.approx(2 * _OBSERVED_COST)
    assert gateway.call_log[-1]["cost_usd"] == pytest.approx(2 * _OBSERVED_COST)
    assert gateway.call_log[-1]["attempt"] == 2
    assert gateway._reserved_spend_usd == 0.0
    assert gateway._budget_reservations == {}


@pytest.mark.asyncio
async def test_cancelled_call_retains_conservative_cost_and_logs_error(monkeypatch):
    completions = _BlockingCompletions()
    gateway = _paid_gateway(monkeypatch, completions, cap=_cap(1.5))

    task = asyncio.create_task(gateway.query("prompt", model="upstage/solar-pro4"))
    await completions.started.wait()
    assert gateway._reserved_spend_usd > 0

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert gateway._reserved_spend_usd == 0.0
    assert gateway._budget_reservations == {}
    assert gateway.spend_usd > 0, "the provider may have accepted the cancelled request"
    assert gateway.call_log[-1]["cost_usd"] == gateway.spend_usd
    assert gateway.call_log[-1]["error"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_during_retry_backoff_keeps_prior_ambiguous_cost(monkeypatch):
    backoff_started = asyncio.Event()
    backoff_release = asyncio.Event()

    async def blocking_sleep(_delay):
        backoff_started.set()
        await backoff_release.wait()

    monkeypatch.setattr(asyncio, "sleep", blocking_sleep)
    gateway = _paid_gateway(monkeypatch, _FailingCompletions(), cap=_cap(1.5))
    # Make the synthetic error retryable so query enters the backoff await.
    gateway.client = _Client(type(
        "RetryingCompletions",
        (),
        {"create": lambda self, **kwargs: _raise_timeout()},
    )())

    task = asyncio.create_task(gateway.query("prompt", model="upstage/solar-pro4"))
    await backoff_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert gateway._reserved_spend_usd == 0.0
    assert gateway._budget_reservations == {}
    assert gateway.spend_usd > 0, "the timed-out first attempt remains ambiguous"
    assert gateway.call_log[-1]["cost_usd"] == gateway.spend_usd
    assert gateway.call_log[-1]["error"] == "CANCELLED"


async def _raise_timeout():
    raise TimeoutError("temporary timeout")


@pytest.mark.asyncio
async def test_cache_hit_bypasses_paid_reservation(monkeypatch):
    gateway = _paid_gateway(monkeypatch, _SlowCompletions(), cap="0.000001")
    gateway.cache = type(
        "Cache",
        (),
        {
            "is_cachable": lambda self, prompt, images: True,
            "make_key": lambda self, **kwargs: "cached-key",
            "get": lambda self, key: "cached",
        },
    )()

    assert await gateway.query("prompt", model="upstage/solar-pro4") == "cached"
    assert gateway.spend_usd == 0.0
    assert gateway._reserved_spend_usd == 0.0
    assert gateway.call_log[-1]["cache_hit"] is True
    assert gateway.call_log[-1]["cost_usd"] == 0.0
