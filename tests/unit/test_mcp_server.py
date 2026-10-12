"""FAZ D · D1 — MCP sunucusu: protokol + mandal testleri.

Kilitlenen iddialar:
    * Dual protokol: legacy el sıkışma VE stateless (sürüm ``_meta``'da).
    * Sürüm anlaşmazlığı sessizce en yenisi sanılmaz; açık hata + liste döner.
    * Yetenek çağrıları içeridekilerle AYNI kapılardan geçer: kasa kapalıysa
      hiçbir yetenek koşmaz; hız sınırı dolduysa koşmaz; çocuk beyanı varsa
      koşmaz. Reddin sebebi makine-okunur.
    * stdio kanalı yalnız protokol mesajı taşır (tek bozuk satır kanalı düşürmez).

Hiçbir test ağa çıkmaz: kasa durumu ya taklit edilir ya yerel bir uçtan okunur.
"""

from __future__ import annotations

import json

import pytest

from agent_core.capabilities import bootstrap
from agent_core.mcp import protocol as p
from agent_core.mcp import server as mcp_server
from agent_core.mcp.state_bridge import SlidingWindowLimiter
from agent_core.mcp.status import STATUS_TOOL_NAME

STATELESS_META = {p.META_VERSION_KEY: p.PROTOCOL_VERSION}


@pytest.fixture()
def open_vault(monkeypatch):
    """Kasa AÇIK: çağrılar politika kapılarına kadar gider."""
    monkeypatch.setattr(
        mcp_server, "vault_state", lambda client_id="default", *, env=None, timeout=2.0: (False, "")
    )


@pytest.fixture()
def locked_vault(monkeypatch):
    """Kasa KİLİTLİ: hiçbir yetenek koşmamalı."""
    monkeypatch.setattr(
        mcp_server,
        "vault_state",
        lambda client_id="default", *, env=None, timeout=2.0: (True, "vault_api_unreachable:URLError"),
    )


def _server(**kwargs) -> mcp_server.MCPServer:
    return mcp_server.MCPServer(**kwargs)


async def _call(server, method: str, params: dict | None = None, *, rid: int = 1):
    message = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        message["params"] = params
    return await server.handle(message)


class TestHandshake:
    async def test_initialize_echoes_supported_version(self):
        response = await _call(_server(), "initialize", {"protocolVersion": "2025-06-18"})
        result = response["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert result["serverInfo"]["name"] == mcp_server.SERVER_NAME
        assert result["capabilities"] == {"tools": {"listChanged": False}}

    async def test_initialize_with_unknown_version_answers_with_newest(self):
        response = await _call(_server(), "initialize", {"protocolVersion": "1999-01-01"})
        assert response["result"]["protocolVersion"] == p.PROTOCOL_VERSION

    async def test_legacy_session_requires_initialize_first(self):
        server = _server()
        response = await _call(server, "tools/list")
        assert response["error"]["code"] == p.ErrorCode.SERVER_NOT_INITIALIZED

    async def test_stateless_request_needs_no_handshake(self):
        server = _server()
        response = await _call(server, "tools/list", {"_meta": STATELESS_META})
        assert "result" in response and len(response["result"]["tools"]) > 1

    async def test_unsupported_meta_version_is_explicit(self):
        response = await _call(
            _server(), "tools/list", {"_meta": {p.META_VERSION_KEY: "1999-01-01"}}
        )
        error = response["error"]
        assert error["code"] == p.ErrorCode.UNSUPPORTED_PROTOCOL_VERSION
        assert error["data"]["supportedVersions"] == list(p.SUPPORTED_PROTOCOL_VERSIONS)

    async def test_notifications_get_no_response(self):
        server = _server()
        assert await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        assert await server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None

    async def test_server_discover_reports_versions_and_identity(self):
        response = await _call(_server(), "server/discover", {"_meta": STATELESS_META})
        result = response["result"]
        assert result["supportedVersions"] == list(p.SUPPORTED_PROTOCOL_VERSIONS)
        assert result["_meta"][p.META_SERVER_INFO_KEY]["name"] == mcp_server.SERVER_NAME
        assert result["resultType"] == "complete"
        assert result["ttlMs"] > 0 and result["cacheScope"] == "public"


class TestToolsListing:
    async def test_tools_list_matches_registry_plus_status_tool(self, open_vault):
        registry = bootstrap()
        response = await _call(_server(), "tools/list", {"_meta": STATELESS_META})
        tools = response["result"]["tools"]
        assert len(tools) == len(registry.ids()) + 1
        assert tools[0]["name"] == STATUS_TOOL_NAME
        assert {t["title"] for t in tools[1:]} == set(registry.ids())

    async def test_tool_list_is_deterministic(self, open_vault):
        server = _server()
        first = await _call(server, "tools/list", {"_meta": STATELESS_META})
        second = await _call(server, "tools/list", {"_meta": STATELESS_META}, rid=2)
        assert first["result"]["tools"] == second["result"]["tools"]

    async def test_listing_carries_cache_fields_only_on_current_version(self):
        server = _server()
        current = await _call(server, "tools/list", {"_meta": STATELESS_META})
        legacy = await _call(server, "initialize", {"protocolVersion": "2025-06-18"})
        assert "result" in legacy
        old_list = await _call(server, "tools/list", rid=3)
        assert "ttlMs" in current["result"]
        assert "ttlMs" not in old_list["result"]

    async def test_resources_are_not_claimed(self):
        response = await _call(_server(), "resources/list", {"_meta": STATELESS_META})
        assert response["error"]["code"] == p.ErrorCode.METHOD_NOT_FOUND
        assert "yalnız 'tools'" in response["error"]["message"]

    async def test_unknown_method_is_rejected(self):
        response = await _call(_server(), "tools/fly", {"_meta": STATELESS_META})
        assert response["error"]["code"] == p.ErrorCode.METHOD_NOT_FOUND

    async def test_ping_and_log_level_are_answered(self):
        server = _server()
        assert (await _call(server, "ping", {"_meta": STATELESS_META}))["result"] == {}
        assert (await _call(server, "logging/setLevel", {"_meta": STATELESS_META}))["result"] == {}


class TestGates:
    async def test_locked_vault_blocks_every_capability(self, locked_vault):
        response = await _call(
            _server(),
            "tools/call",
            {
                "name": "extractor_text_language",
                "arguments": {"subject": "Merhaba dünya, bugün hava güzel."},
                "_meta": STATELESS_META,
            },
        )
        rendered = response["result"]
        assert rendered["isError"] is True
        structured = rendered["structuredContent"]
        assert structured["denied_by"] == "vault"
        assert structured["evidence_count"] == 0

    async def test_open_vault_runs_capability_and_returns_evidence(self, open_vault):
        response = await _call(
            _server(),
            "tools/call",
            {
                "name": "extractor_text_language",
                "arguments": {"subject": "Merhaba dünya, bugün hava çok güzel ve dışarı çıkmak istiyorum."},
                "_meta": STATELESS_META,
            },
        )
        rendered = response["result"]
        assert rendered["isError"] is False
        structured = rendered["structuredContent"]
        assert structured["evidence_count"] == 1
        assert structured["notes"]["language"] == "tr"

    async def test_disabled_env_gate_denies_with_gate_name(self, open_vault, monkeypatch):
        monkeypatch.delenv("ENABLE_LOCAL_TRANSLATE", raising=False)
        response = await _call(
            _server(),
            "tools/call",
            {
                "name": "extractor_text_translate_local",
                "arguments": {"subject": "Merhaba", "target": "en"},
                "_meta": STATELESS_META,
            },
        )
        structured = response["result"]["structuredContent"]
        assert structured["denied_by"] == "ENABLE_LOCAL_TRANSLATE"
        assert structured["unavailable_reason"] == "policy:gate_disabled"

    async def test_enabled_flag_lets_the_call_reach_the_engine(self, open_vault, monkeypatch):
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "1")
        response = await _call(
            _server(),
            "tools/call",
            {
                "name": "extractor_text_translate_local",
                "arguments": {"subject": "Merhaba", "target": "en"},
                "_meta": STATELESS_META,
            },
        )
        structured = response["result"]["structuredContent"]
        assert structured["denied_by"] is None
        # Motor yoksa çeviri uydurulmaz; ama çağrı kapıdan GEÇTİ.
        assert structured["available"] is False
        assert "no_engine" in (structured["unavailable_reason"] or "")

    async def test_rate_limit_blocks_after_quota(self, open_vault):
        server = _server(limiter=SlidingWindowLimiter(limit=1, window_seconds=60))
        params = {
            "name": "extractor_text_language",
            "arguments": {"subject": "Merhaba dünya, bugün hava çok güzel."},
            "_meta": STATELESS_META,
        }
        first = await _call(server, "tools/call", params)
        second = await _call(server, "tools/call", params, rid=2)
        assert first["result"]["structuredContent"]["denied_by"] is None
        limited = second["result"]["structuredContent"]
        assert limited["denied_by"] == "rate"
        assert limited["unavailable_reason"] == "policy:rate_limited"

    async def test_rate_limit_is_per_tool(self, open_vault):
        server = _server(limiter=SlidingWindowLimiter(limit=1, window_seconds=60))
        await _call(
            server,
            "tools/call",
            {"name": STATUS_TOOL_NAME, "arguments": {}, "_meta": STATELESS_META},
        )
        other = await _call(
            server,
            "tools/call",
            {
                "name": "extractor_text_language",
                "arguments": {"subject": "Merhaba dünya, bugün hava çok güzel."},
                "_meta": STATELESS_META,
            },
            rid=2,
        )
        assert other["result"]["structuredContent"]["denied_by"] is None

    async def test_operator_declared_minor_freezes_the_subject(self, open_vault, monkeypatch):
        monkeypatch.setenv("PINEAL_MCP_MINOR_SUBJECTS", "cocuk_hedef")
        response = await _call(
            _server(),
            "tools/call",
            {
                "name": "extractor_text_language",
                "arguments": {"subject": "cocuk_hedef"},
                "_meta": STATELESS_META,
            },
        )
        structured = response["result"]["structuredContent"]
        assert structured["denied_by"] == "minor_safe"
        assert (structured["unavailable_reason"] or "").startswith("minor:")
        assert structured["evidence_count"] == 0

    async def test_minor_declaration_does_not_touch_other_subjects(self, open_vault, monkeypatch):
        monkeypatch.setenv("PINEAL_MCP_MINOR_SUBJECTS", "cocuk_hedef")
        response = await _call(
            _server(),
            "tools/call",
            {
                "name": "extractor_text_language",
                "arguments": {"subject": "Merhaba dünya, bugün hava çok güzel."},
                "_meta": STATELESS_META,
            },
        )
        assert response["result"]["structuredContent"]["denied_by"] is None


class TestBadCalls:
    async def test_unknown_tool_is_invalid_params_not_silent_success(self):
        response = await _call(
            _server(), "tools/call", {"name": "yok_boyle_arac", "arguments": {}, "_meta": STATELESS_META}
        )
        assert response["error"]["code"] == p.ErrorCode.INVALID_PARAMS
        assert "araç yok" in response["error"]["message"]
        assert "extractor_text_language" in response["error"]["message"]

    async def test_missing_tool_name_is_rejected(self):
        response = await _call(_server(), "tools/call", {"arguments": {}, "_meta": STATELESS_META})
        assert response["error"]["code"] == p.ErrorCode.INVALID_PARAMS

    async def test_non_object_arguments_rejected(self):
        response = await _call(
            _server(),
            "tools/call",
            {"name": STATUS_TOOL_NAME, "arguments": [1, 2], "_meta": STATELESS_META},
        )
        assert response["error"]["code"] == p.ErrorCode.INVALID_PARAMS


class TestStatusTool:
    async def test_status_reports_capabilities_and_vault(self, locked_vault):
        response = await _call(
            _server(),
            "tools/call",
            {"name": STATUS_TOOL_NAME, "arguments": {}, "_meta": STATELESS_META},
        )
        rendered = response["result"]
        assert rendered["isError"] is False
        text = rendered["content"][0]["text"]
        assert "KASA: KİLİTLİ" in text
        assert f"yetenek sayısı: {len(bootstrap().ids())}" in text
        structured = rendered["structuredContent"]
        assert structured["capability_count"] == len(bootstrap().ids())
        assert all(row["policy_allowed"] is False for row in structured["capabilities"])

    async def test_status_reports_open_vault(self, open_vault):
        response = await _call(
            _server(),
            "tools/call",
            {"name": STATUS_TOOL_NAME, "arguments": {}, "_meta": STATELESS_META},
        )
        text = response["result"]["content"][0]["text"]
        assert "KASA: AÇIK" in text

    async def test_status_does_not_produce_evidence(self, open_vault):
        response = await _call(
            _server(),
            "tools/call",
            {"name": STATUS_TOOL_NAME, "arguments": {}, "_meta": STATELESS_META},
        )
        # Durum aracı kanıt ÜRETMEZ: envanter raporu, saha bulgusu değildir.
        assert "evidence_count" not in response["result"]["structuredContent"]


class TestStdioStream:
    async def test_stdout_only_carries_protocol_messages(self, open_vault):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": STATELESS_META}}),
            "{ bu bozuk json",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
        ]
        queue = list(lines) + [""]
        written: list[dict] = []

        async def reader() -> str:
            return queue.pop(0) if queue else ""

        server = _server()
        await server.serve_stream(reader, written.append)

        assert len(written) == 3  # üç satır → üç yanıt (ikisi hata)
        for payload in written:
            assert payload["jsonrpc"] == "2.0"
            json.dumps(payload)  # serileşmeyen bir şey yazılmadı
        assert written[1]["error"]["code"] == p.ErrorCode.PARSE_ERROR
        assert written[1]["id"] is None
        assert written[2]["result"] == {}
        # Bağlantı koptu sanılmasın: döngü EOF ile temiz kapanır.

    async def test_unexpected_exception_keeps_channel_alive(self, monkeypatch):
        server = _server()

        async def boom(*args, **kwargs):
            raise RuntimeError("beklenmedik")

        monkeypatch.setattr(server, "_dispatch", boom)
        response = await _call(server, "tools/list", {"_meta": STATELESS_META})
        assert response["error"]["code"] == p.ErrorCode.INTERNAL_ERROR
        assert "RuntimeError" in response["error"]["message"]


def test_server_version_comes_from_version_file():
    import pathlib

    expected = pathlib.Path(mcp_server.__file__).resolve().parents[2].joinpath("VERSION")
    assert mcp_server.server_version() == expected.read_text(encoding="utf-8").strip()
