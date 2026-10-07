"""FAZ D · D1 — ``/api/mcp/status`` uçtan uca (kokpit + dış istemci bilgisi).

Kilitlenen iddialar:
    * Araç sayısı ``CapabilityRegistry``den okunur — uydurma sabit sayı yok.
    * Kasa mandalı ``/api/initiate`` ile AYNI kapıdan gelir: kapalıysa
      ``vault_locked: true`` ve mesaj açıkça "KİLİTLİ" der.
    * Uç hiçbir yeteneği KOŞTURMAZ (yan etki yok, yalnız rapor).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import api


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture()
def vault(client):
    client.get("/api/telemetry?client_id=mcp")
    room = api.get_room("mcp")
    yield room["vault"]
    room["vault"].pop("or_key", None)


class TestMcpStatus:
    def test_reports_registry_derived_counts(self, client, vault, monkeypatch):
        monkeypatch.delenv("ENABLE_MAIGRET", raising=False)
        payload = client.get("/api/mcp/status?client_id=mcp").json()
        from agent_core.capabilities import bootstrap
        from agent_core.mcp.tools import build_tools

        registry = bootstrap()
        assert payload["available"] is True
        assert payload["capabilities"] == len(registry.ids())
        assert payload["tools"] == len(build_tools(registry)) + 1
        assert payload["transport"] == "stdio"
        assert payload["command"] == "python -m agent_core.mcp"

    def test_publishes_supported_protocols(self, client, vault):
        from agent_core.mcp import protocol

        payload = client.get("/api/mcp/status?client_id=mcp").json()
        assert payload["protocol_current"] == protocol.PROTOCOL_VERSION
        assert payload["protocol_supported"] == list(protocol.SUPPORTED_PROTOCOL_VERSIONS)

    def test_locked_vault_is_reported_honestly(self, client):
        client.get("/api/telemetry?client_id=kilitli")
        api.get_room("kilitli")["vault"].pop("or_key", None)
        payload = client.get("/api/mcp/status?client_id=kilitli").json()
        assert payload["vault_locked"] is True
        assert "KİLİTLİ" in payload["message"]

    def test_open_vault_is_reported(self, client, vault):
        vault["or_key"] = True
        payload = client.get("/api/mcp/status?client_id=mcp").json()
        assert payload["vault_locked"] is False
        assert "MCP açık" in payload["message"]

    def test_endpoint_does_not_run_any_capability(self, client, vault, monkeypatch):
        """Durum ucu yan etkisizdir: yetenek koşusu kaydedilmez."""
        calls: list[str] = []

        from agent_core.capabilities.runner import CapabilityRunner

        original = CapabilityRunner.run

        async def spy(self, cap_id, ctx=None, **kwargs):
            calls.append(cap_id)
            return await original(self, cap_id, ctx, **kwargs)

        monkeypatch.setattr(CapabilityRunner, "run", spy)
        client.get("/api/mcp/status?client_id=mcp")
        assert calls == []

    def test_rate_limit_is_published(self, client, vault, monkeypatch):
        monkeypatch.setenv("PINEAL_MCP_RATE_LIMIT", "7")
        monkeypatch.setenv("PINEAL_MCP_RATE_WINDOW", "30")
        payload = client.get("/api/mcp/status?client_id=mcp").json()
        assert payload["rate_limit"] == {"limit": 7, "window_seconds": 30.0}
