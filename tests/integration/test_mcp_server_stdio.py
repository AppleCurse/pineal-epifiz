"""FAZ D · D1 — MCP sunucusu UÇTAN UCA: gerçek süreç, gerçek stdio, gerçek kapılar.

Bu test alt süreci (``python -m agent_core.mcp``) gerçekten başlatır ve tel
üzerinden konuşur; taklit edilen tek şey Pineal API'sinin kasa cevabıdır
(çünkü testte tam API ayağa kaldırmak, ölçülen şeyi değiştirirdi).

Kilitlenen iddialar:
    * stdout YALNIZ protokol mesajı taşır (tek satır günlük kanalı bozar).
    * Kasa açıkken yetenek koşar ve KANIT döner; kanıt kimliği ``ev_`` ile başlar.
    * Kasa kapalıyken hiçbir yetenek koşmaz; reddin sebebi makine-okunur.
    * Sunucu sonsuz döngüye girmez: stdin kapanınca (EOF) temiz çıkar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from agent_core.mcp import protocol as p

REPO_ROOT = Path(__file__).resolve().parents[2]
STATELESS_META = {p.META_VERSION_KEY: p.PROTOCOL_VERSION}


class _VaultAPI:
    """Yerel API taklidi: yalnız ``/api/vault/status`` cevaplanır."""

    def __init__(self, locked: bool):
        self.locked = locked
        self.hits = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.hits += 1
                body = json.dumps({"locked": outer.locked, "can_scrape": not outer.locked}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _run_session(messages: list[dict], *, api_url: str, extra_env: dict | None = None) -> tuple[list[dict], str]:
    """Mesajları stdin'e yazar, stdout'u JSON satırları olarak toplar."""
    payload = "".join(json.dumps(message) + "\n" for message in messages)
    env = {
        **os.environ,
        "PINEAL_API_URL": api_url,
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONIOENCODING": "utf-8",
        **(extra_env or {}),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "agent_core.mcp"],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, f"MCP sunucusu çöktü: {proc.stderr[-800:]}"
    responses = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        responses.append(json.loads(line))  # günlük sızarsa burada patlar
    return responses, proc.stderr


@pytest.fixture()
def open_api():
    api = _VaultAPI(locked=False)
    yield api
    api.close()


@pytest.fixture()
def locked_api():
    api = _VaultAPI(locked=True)
    yield api
    api.close()


def _tool_call(name: str, arguments: dict, rid: int = 10) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments, "_meta": STATELESS_META},
    }


class TestStatelessSession:
    def test_handshake_list_and_call_over_real_pipe(self, open_api):
        responses, stderr = _run_session(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": STATELESS_META}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": STATELESS_META}},
                _tool_call(
                    "extractor_text_language",
                    {"subject": "Merhaba dünya, bugün hava çok güzel ve dışarı çıkmak istiyorum."},
                ),
            ],
            api_url=open_api.url,
        )

        discover, listing, call = responses
        assert discover["result"]["supportedVersions"][0] == p.PROTOCOL_VERSION
        assert len(listing["result"]["tools"]) >= 15
        assert listing["result"]["resultType"] == "complete"

        rendered = call["result"]
        assert rendered["isError"] is False
        structured = rendered["structuredContent"]
        assert structured["evidence_count"] == 1
        assert structured["evidence_ids"][0].startswith("ev_")
        assert structured["notes"]["language"] == "tr"
        assert "protokol" not in stderr  # günlük stdout'a sızmadı

    def test_stdout_lines_are_all_json(self, open_api):
        responses, _stderr = _run_session(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"_meta": STATELESS_META}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/fly", "params": {"_meta": STATELESS_META}},
            ],
            api_url=open_api.url,
        )
        assert responses[0]["result"] == {}
        assert responses[1]["error"]["code"] == p.ErrorCode.METHOD_NOT_FOUND


class TestVaultMatters:
    def test_locked_vault_denies_over_the_wire(self, locked_api):
        responses, _ = _run_session(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                _tool_call(
                    "extractor_text_language",
                    {"subject": "Merhaba dünya, bugün hava çok güzel."},
                ),
            ],
            api_url=locked_api.url,
        )
        # initialize yanıtı + çağrı yanıtı; ikincisi dürüst ret olmalı.
        rendered = responses[-1]["result"]
        assert rendered["isError"] is True
        assert rendered["structuredContent"]["denied_by"] == "vault"
        assert rendered["structuredContent"]["evidence_count"] == 0

    def test_same_call_runs_when_vault_is_open(self, open_api):
        responses, _ = _run_session(
            [
                _tool_call(
                    "extractor_text_language",
                    {"subject": "Merhaba dünya, bugün hava çok güzel."},
                    rid=1,
                )
            ],
            api_url=open_api.url,
        )
        assert responses[0]["result"]["isError"] is False
        assert responses[0]["result"]["structuredContent"]["evidence_count"] == 1
        assert open_api.hits >= 1  # kanıt: kasa durumu GERÇEKTEN API'den okundu

    def test_status_tool_reports_registry_and_vault(self, locked_api):
        responses, _ = _run_session(
            [
                _tool_call("pineal_status", {}, rid=1),
            ],
            api_url=locked_api.url,
        )
        structured = responses[0]["result"]["structuredContent"]
        assert structured["capability_count"] == len(structured["capabilities"])
        assert structured["vault"]["vault_locked"] is True
        assert all(row["policy_allowed"] is False for row in structured["capabilities"])


class TestNoSecretLeak:
    def test_env_keys_are_not_echoed_by_the_server(self, open_api):
        """Sunucu ortam sırlarını ne döndürür ne loglar (kasa dışında sır yok)."""
        responses, stderr = _run_session(
            [
                _tool_call("pineal_status", {}, rid=1),
            ],
            api_url=open_api.url,
            extra_env={"OPENROUTER_API_KEY": "sk-or-v1-TEST-SECRET-DO-NOT-ECHO"},
        )
        blob = json.dumps(responses, ensure_ascii=False) + stderr
        assert "TEST-SECRET-DO-NOT-ECHO" not in blob
