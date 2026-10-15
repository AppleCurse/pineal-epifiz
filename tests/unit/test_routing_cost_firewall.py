"""FINAL routing firewall over the real RoutedChatExecutor code path.

These tests drive the native routed executor end-to-end (no executor mock):
policy denial, provider default-model substitution, capability selection, and
the telemetry contract (requested/actual model, fallback_reason, quota_status).
"""

import socket
from types import SimpleNamespace

import pytest

from agent_core.services.final_routing_policy import PaidEscalationDenied
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.routed_chat import RoutedChatExecutor


def _fake_resolver(host, port, family=0, socktype=0):
    resolved_family = socket.AF_INET
    return [(resolved_family, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def _nous_executor(*groups, environ=None) -> RoutedChatExecutor:
    connections = [
        {
            "id": "nous-default",
            "provider_id": "nous-research",
            "connection_type": "api_key",
            "credential_env": "NOUS_API_KEY",
            "enabled": True,
        },
    ]
    return RoutedChatExecutor.from_mapping(
        {
            "schema_version": 1,
            "tenant_id": "test-tenant",
            "connections": connections,
            "model_groups": dict(groups),
        },
        environ={"NOUS_API_KEY": "nk-test"} if environ is None else environ,
        resolver=_fake_resolver,
    )


def _fake_gateway(monkeypatch, handler) -> tuple[LLMGateway, dict]:
    gateway = LLMGateway()
    gateway.set_key("nk-test", unlock_live=True)
    gateway.cache = None

    state = {"calls": 0}

    class Completions:
        async def create(self, **kwargs):
            state["calls"] += 1
            return handler(kwargs)

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions()),
    )
    monkeypatch.setattr(gateway, "_client_for_route", lambda route: fake_client)
    return gateway, state


def _ok(model: str, content: str = "ok"):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


class _StatusError(Exception):
    def __init__(self, status_code: int, message: str = "boom"):
        super().__init__(message)
        self.status_code = status_code


# --------------------------------------------------------------------------- #
# Paid escalation firewall
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_paid_route_is_denied_without_escalation(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor(("frontier_daily", ["nous-research/openai/gpt-5.6-luna"]))
    gateway, state = _fake_gateway(monkeypatch, lambda kwargs: _ok("openai/gpt-5.6-luna"))

    with pytest.raises(PaidEscalationDenied):
        await executor.chat_completion(
            gateway,
            messages=[{"role": "user", "content": "hi"}],
            model="frontier_daily",
        )
    assert state["calls"] == 0, "paid route must never reach the network without permission"


@pytest.mark.asyncio
async def test_free_route_executes_without_escalation(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor(("fast", ["nous-research/poolside/laguna-s-2.1:free"]))
    gateway, state = _fake_gateway(monkeypatch, lambda kwargs: _ok("poolside/laguna-s-2.1:free"))

    result = await executor.chat_completion(
        gateway,
        messages=[{"role": "user", "content": "hi"}],
        model="fast",
    )
    assert state["calls"] == 1
    assert result.result.response.model == "poolside/laguna-s-2.1:free"


@pytest.mark.asyncio
async def test_paid_route_executes_when_escalation_enabled(monkeypatch):
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    executor = _nous_executor(("frontier_daily", ["nous-research/openai/gpt-5.6-luna"]))
    gateway, state = _fake_gateway(monkeypatch, lambda kwargs: _ok("openai/gpt-5.6-luna"))

    result = await executor.chat_completion(
        gateway,
        messages=[{"role": "user", "content": "hi"}],
        model="frontier_daily",
    )
    assert state["calls"] == 1
    record = gateway.call_log[-1]
    assert record["requested_model"] == "openai/gpt-5.6-luna"
    assert record["actual_model"] == "openai/gpt-5.6-luna"
    assert record["provider"] == "nous-research"
    assert record["quota_status"] is not None
    assert result.result.call_id == record["call_id"]


# --------------------------------------------------------------------------- #
# Provider default-model substitution firewall
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_provider_default_substitution_is_denied(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor(("fast", ["nous-research/poolside/laguna-s-2.1:free"]))
    gateway, state = _fake_gateway(monkeypatch, lambda kwargs: _ok("provider-default-model"))

    with pytest.raises(RuntimeError, match="MODEL_SUBSTITUTION_DENIED"):
        await executor.chat_completion(
            gateway,
            messages=[{"role": "user", "content": "hi"}],
            model="fast",
        )
    assert state["calls"] == 1
    assert any(
        "MODEL_SUBSTITUTION_DENIED" in (record.get("error") or "")
        for record in gateway.call_log
    )


# --------------------------------------------------------------------------- #
# Fallback semantics + telemetry fallback_reason
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_empty_choices_fail_over_to_next_route_without_same_route_retry(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor((
        "code_expert",
        [
            "nous-research/poolside/laguna-s-2.1:free",
            "nous-research/poolside/laguna-xs-2.1:free",
        ],
    ))
    seen: list[str] = []

    def handler(kwargs):
        seen.append(kwargs["model"])
        if len(seen) == 1:
            return SimpleNamespace(model=kwargs["model"], usage=None, choices=[])
        return _ok(kwargs["model"])

    gateway, state = _fake_gateway(monkeypatch, handler)
    result = await executor.chat_completion(
        gateway,
        messages=[{"role": "user", "content": "hi"}],
        model="code_expert",
    )

    assert state["calls"] == 2
    assert seen == ["poolside/laguna-s-2.1:free", "poolside/laguna-xs-2.1:free"]
    failed = [record for record in gateway.call_log if record.get("error")][0]
    success = [record for record in gateway.call_log if record.get("error") is None][0]
    assert failed["error"] == "ProviderEmptyResponseError"
    assert failed["cost_usd"] >= 0.0
    assert success["fallback_reason"] == "SERVER_ERROR"
    assert result.result.response.model == "poolside/laguna-xs-2.1:free"


@pytest.mark.asyncio
async def test_fallback_reason_is_recorded_on_actual_model(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor((
        "code_expert",
        ["nous-research/poolside/laguna-s-2.1:free", "nous-research/poolside/laguna-xs-2.1:free"],
    ))
    seen: list[str] = []

    def handler(kwargs):
        seen.append(kwargs["model"])
        if kwargs["model"] == "poolside/laguna-s-2.1:free":
            raise _StatusError(503)
        return _ok("poolside/laguna-xs-2.1:free")

    gateway, state = _fake_gateway(monkeypatch, handler)
    result = await executor.chat_completion(
        gateway,
        messages=[{"role": "user", "content": "hi"}],
        model="code_expert",
    )
    assert seen == ["poolside/laguna-s-2.1:free", "poolside/laguna-xs-2.1:free"]
    success = [r for r in gateway.call_log if r.get("error") is None][0]
    assert success["actual_model"] == "poolside/laguna-xs-2.1:free"
    assert success["fallback_reason"] == "SERVER_ERROR"
    assert result.result.call_id == success["call_id"]


@pytest.mark.asyncio
async def test_429_quota_exhaustion_marks_fallback_reason(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor((
        "code_expert",
        ["nous-research/poolside/laguna-s-2.1:free", "nous-research/poolside/laguna-xs-2.1:free"],
    ))

    class QuotaError(Exception):
        status_code = 429

        def __init__(self):
            super().__init__("insufficient_quota: out of credits")

    def handler(kwargs):
        if kwargs["model"] == "poolside/laguna-s-2.1:free":
            raise QuotaError()
        return _ok("poolside/laguna-xs-2.1:free")

    gateway, state = _fake_gateway(monkeypatch, handler)
    await executor.chat_completion(
        gateway,
        messages=[{"role": "user", "content": "hi"}],
        model="code_expert",
    )
    failed = [r for r in gateway.call_log if r.get("error")][0]
    assert failed["fallback_reason"] == "429_QUOTA_EXHAUSTED"


# --------------------------------------------------------------------------- #
# Capability selection
# --------------------------------------------------------------------------- #
def test_vision_group_selects_vision_capable_model_only(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor((
        "vision",
        ["nous-research/meituan/longcat-2.0", "nous-research/anthropic/claude-sonnet-5"],
    ))
    plan = executor.plan(
        "vision",
        required_capabilities={"vision"},
    )
    vision_targets = [
        candidate.target.model.canonical_id
        for candidate in plan.candidates
        if candidate.eligible
    ]
    # LongCat 2.0 is not vision-capable and must be filtered out.
    assert vision_targets == ["nous-research/anthropic/claude-sonnet-5"]


def test_non_vision_task_rejects_vision_requirement(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    executor = _nous_executor(("fast", ["nous-research/poolside/laguna-s-2.1:free"]))
    plan = executor.plan("fast", required_capabilities={"vision"})
    assert plan.attempt_order == ()
