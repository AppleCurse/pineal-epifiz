"""Unit contract tests for RoutedChatExecutor (agent_core/services/routed_chat.py).

These lock the public/loading contract of the native LLM routing runtime
without any network access: configuration parsing, fail-safe env handling,
and the mode/tool/streaming guards that must reject before a request leaves
the process.

Note: an earlier unit test file for this module was lost during the
``bb69eb6`` recovery incident and never pushed. This file restores that
coverage against the current implementation.
"""

from pathlib import Path

import pytest

from agent_core.services.routed_chat import (
    RoutedChatExecutor,
    RoutingRuntimeError,
    llm_backend_mode_from_env,
    routing_runtime_from_env,
)
from agent_core.services.unified_router import RoutingStrategy

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "config" / "router.example.json"


def _base_config() -> dict:
    return {
        "schema_version": 1,
        "tenant_id": "test-tenant",
        "connections": [
            {
                "id": "or",
                "provider_id": "openrouter",
                "connection_type": "api_key",
                "credential_env": "OPENROUTER_API_KEY",
                "enabled": True,
            },
            {
                "id": "ollama",
                "provider_id": "ollama-local",
                "connection_type": "local",
                "enabled": True,
            },
        ],
        "model_groups": {
            "fast": [
                "openrouter/upstage/solar-pro4",
                "openrouter/inclusionai/ling-3.0-flash",
            ],
            "local": ["ollama-local/llama3.2"],
        },
    }


def _executor(**overrides) -> RoutedChatExecutor:
    config = _base_config()
    config.update(overrides)
    return RoutedChatExecutor.from_mapping(config)


# ---------------------------------------------------------------- loading

def test_shipped_example_config_loads():
    executor = RoutedChatExecutor.from_file(EXAMPLE_CONFIG)
    # 2026-09-02 matrix: fast/depth/vision groups + local offline group.
    assert set(executor.model_groups) == {"fast", "depth", "vision", "local"}
    assert executor.handles("fast") is True
    assert executor.handles("depth") is True
    assert executor.handles("vision") is True
    assert executor.handles("local") is True
    assert executor.handles("unknown") is False


def test_schema_version_must_be_one():
    with pytest.raises(RoutingRuntimeError, match="schema_version"):
        RoutedChatExecutor.from_mapping({})


def test_connections_must_be_non_empty():
    config = _base_config()
    config["connections"] = []
    with pytest.raises(RoutingRuntimeError, match="connections"):
        RoutedChatExecutor.from_mapping(config)


def test_connection_requires_openai_chat_protocol():
    config = _base_config()
    config["connections"] = [
        {
            "id": "anthropic",
            "provider_id": "anthropic",
            "connection_type": "api_key",
            "credential_env": "ANTHROPIC_API_KEY",
            "enabled": True,
        }
    ]
    with pytest.raises(RoutingRuntimeError, match="openai_chat"):
        RoutedChatExecutor.from_mapping(config)


def test_oauth_connection_type_is_declared_but_not_executable_in_routed_runtime():
    config = _base_config()
    config["connections"][0] = {
        "id": "or-oauth",
        "provider_id": "openrouter",
        "connection_type": "oauth_subscription",
        "credential_env": "OPENROUTER_OAUTH_TOKEN",
        "enabled": True,
    }
    with pytest.raises(RoutingRuntimeError, match="api_key and local"):
        RoutedChatExecutor.from_mapping(config)


def test_connection_credential_env_must_be_uppercase():
    config = _base_config()
    config["connections"][0]["credential_env"] = "openrouter_api_key"
    with pytest.raises(RoutingRuntimeError, match="uppercase"):
        RoutedChatExecutor.from_mapping(config)


def test_connection_enabled_requires_strict_boolean():
    # JSON string "false" must never coerce to True.
    config = _base_config()
    config["connections"][0]["enabled"] = "false"
    with pytest.raises(RoutingRuntimeError, match="must be a boolean"):
        RoutedChatExecutor.from_mapping(config)


def test_remote_endpoint_override_is_rejected():
    config = _base_config()
    config["connections"][0]["endpoint_override"] = "https://example.com/v1"
    # The specific guard is wrapped by _connection_from_mapping's except clause,
    # which surfaces it as "invalid routing connection".
    with pytest.raises(RoutingRuntimeError, match="invalid routing connection"):
        RoutedChatExecutor.from_mapping(config)


def test_group_without_configured_connection_is_rejected():
    config = _base_config()
    config["connections"] = config["connections"][1:]  # only ollama-local
    config["model_groups"] = {"g": ["openrouter/upstage/solar-pro4"]}
    with pytest.raises(RoutingRuntimeError, match="no configured runtime connection"):
        RoutedChatExecutor.from_mapping(config)


def test_model_pricing_rejects_negative_rates():
    config = _base_config()
    config["model_pricing"] = {
        "openrouter/upstage/solar-pro4": {
            "input_per_million_usd": -1.0,
            "output_per_million_usd": 0.0,
        }
    }
    with pytest.raises(RoutingRuntimeError, match="non-negative"):
        RoutedChatExecutor.from_mapping(config)


def test_from_file_rejects_oversized_config(tmp_path):
    big = tmp_path / "big.json"
    big.write_text("x" * (1_048_576 + 1), encoding="utf-8")
    with pytest.raises(RoutingRuntimeError, match="1 MiB"):
        RoutedChatExecutor.from_file(big)


# ---------------------------------------------------------------- env / rollout

def test_backend_mode_defaults_to_unified(monkeypatch):
    monkeypatch.delenv("PINEAL_LLM_BACKEND", raising=False)
    assert llm_backend_mode_from_env() == "unified"


def test_backend_mode_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("PINEAL_LLM_BACKEND", "garbage")
    with pytest.raises(RoutingRuntimeError, match="legacy or unified"):
        llm_backend_mode_from_env()


def test_routing_runtime_auto_builds_without_config(monkeypatch):
    monkeypatch.delenv("PINEAL_ROUTER_CONFIG", raising=False)
    executor = routing_runtime_from_env()
    assert executor is not None
    assert executor.handles("fast") is True
    assert executor.handles("solar_pro4") is True
    assert executor.handles("upstage/solar-pro4") is True
    assert executor.handles("vision") is True


def test_routing_runtime_adds_official_combo_when_keys_present(monkeypatch):
    monkeypatch.delenv("PINEAL_ROUTER_CONFIG", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    executor = routing_runtime_from_env()
    assert executor is not None
    assert any(
        model.startswith("groq/")
        for model in executor.model_groups["fast"]
    )


def test_routing_runtime_loads_configured_file(monkeypatch):
    monkeypatch.setenv("PINEAL_ROUTER_CONFIG", str(EXAMPLE_CONFIG))
    executor = routing_runtime_from_env()
    assert executor is not None
    assert executor.handles("fast") is True


# ---------------------------------------------------------------- runtime guards

def test_unknown_model_group_is_rejected():
    executor = _executor()
    with pytest.raises(RoutingRuntimeError, match="unknown routed model group"):
        executor.plan("nope")


def test_plan_accepts_registry_alias_and_openrouter_slug():
    executor = routing_runtime_from_env()
    assert executor is not None
    alias_plan = executor.plan("solar_pro4")
    slug_plan = executor.plan("upstage/solar-pro4")
    assert alias_plan.attempt_order
    assert slug_plan.attempt_order
    assert alias_plan.candidates[0].target.model.id == "upstage/solar-pro4"


def test_candidate_models_are_forwarded_to_the_router():
    executor = _executor()
    plan = executor.plan("fast", strategy=RoutingStrategy.PRIORITY)
    assert plan.attempt_order
    models = [candidate.target.model.canonical_id for candidate in plan.candidates if candidate.eligible]
    assert models[0] == "openrouter/upstage/solar-pro4"


@pytest.mark.parametrize(
    "strategy",
    [
        RoutingStrategy.FUSION,
        RoutingStrategy.PIPELINE,
        RoutingStrategy.CONTEXT_RELAY,
    ],
)
def test_tools_with_multi_provider_modes_rejected(strategy):
    import asyncio

    executor = _executor()
    messages = [{"role": "user", "content": "hi"}]
    with pytest.raises(RoutingRuntimeError, match="tool calls"):
        asyncio.run(
            executor.chat_completion(
                None,
                messages=messages,
                model="fast",
                strategy=strategy,
                tools=[{"type": "function", "function": {"name": "ping"}}],
            )
        )


@pytest.mark.parametrize(
    "strategy",
    [
        RoutingStrategy.FUSION,
        RoutingStrategy.PIPELINE,
        RoutingStrategy.CONTEXT_RELAY,
    ],
)
def test_streaming_with_multi_provider_modes_rejected(strategy):
    executor = _executor()
    messages = [{"role": "user", "content": "hi"}]

    async def _run():
        await executor.start_chat_stream(
            None,
            messages=messages,
            model="fast",
            strategy=strategy,
        )

    import asyncio

    with pytest.raises(RoutingRuntimeError, match="streaming"):
        asyncio.run(_run())


@pytest.mark.parametrize(
    ("messages", "response_format"),
    [
        (
            [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}}]}],
            None,
        ),
        (
            [{"role": "user", "content": [{"type": "audio_url", "audio_url": {"url": "https://example.invalid/audio.wav"}}]}],
            None,
        ),
        ([{"role": "user", "content": "Return JSON."}], {"type": "json_object"}),
        (
            [{"role": "user", "content": "Return schema JSON."}],
            {"type": "json_schema", "json_schema": {"name": "result", "schema": {"type": "object"}}},
        ),
    ],
)
def test_undeclared_audio_and_json_capabilities_fail_closed_before_gateway(
    messages, response_format
):
    """Catalog metadata with no declaration must not route these request modes."""
    import asyncio

    executor = _executor()

    async def _run():
        from types import SimpleNamespace

        await executor.chat_completion(
            SimpleNamespace(max_output_tokens=4096),
            messages=messages,
            model="fast",
            response_format=response_format,
        )

    with pytest.raises(RuntimeError, match="ROUTE_UNAVAILABLE"):
        asyncio.run(_run())


def test_streaming_json_mode_is_also_gated_by_declared_capability():
    import asyncio
    from types import SimpleNamespace

    executor = _executor()

    async def _run():
        await executor.start_chat_stream(
            SimpleNamespace(max_output_tokens=4096),
            messages=[{"role": "user", "content": "Return JSON."}],
            model="fast",
            response_format={"type": "json_object"},
        )

    with pytest.raises(RuntimeError, match="ROUTE_UNAVAILABLE"):
        asyncio.run(_run())


def test_unknown_response_format_is_rejected_before_routing():
    import asyncio

    executor = _executor()

    async def _run():
        await executor.chat_completion(
            None,
            messages=[{"role": "user", "content": "hi"}],
            model="fast",
            response_format={"type": "xml_object"},
        )

    with pytest.raises(RoutingRuntimeError, match="response_format.type"):
        asyncio.run(_run())
