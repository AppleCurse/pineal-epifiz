"""FAZ D · D2 — yerel jüri YETENEĞİ: kapılar, kanıt türü, konsensüs sözleşmesi.

Kilitlenen iddialar:
    * Yetenek omurgadadır: kasa + ``ENABLE_LOCAL_JURY`` kapılarından geçer;
      kasa kapalıyken ya da kapı kapalıyken KOŞMAZ (istisna yok).
    * Konsensüs varsa kanıt üretilir ve türü ``inference``dır (model yargısı
      gözlem değildir).
    * Konsensüs YOKSA kanıt üretilmez; koltuk dökümü ``notes`` içinde kalır.
    * Yetenek MCP araç listesinde kendiliğinden görünür (tek kaynak: defter).
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent_core.capabilities import (
    CapabilityContext,
    PolicyState,
    bootstrap,
)
from agent_core.capabilities.runner import CapabilityRunner
from agent_core.mcp.tools import build_tools
from agent_core.services.jury_consensus import VOTE_FALSE, VOTE_VERIFIED

CAP_ID = "verifier.jury.local"
CLAIM = "Hedef hesap 2021'den beri aktif."
EVIDENCE = "Arşiv kaydı: ilk gönderi 2021-03-04."


class _LocalLLM:
    def __init__(self, votes: dict[str, str]):
        self.votes = votes
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                vote = outer.votes.get(request.get("model", ""), VOTE_VERIFIED)
                content = json.dumps({"vote": vote, "confidence": 0.8, "reason": "t"})
                body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def local_llm():
    stub = _LocalLLM({"m1": VOTE_VERIFIED, "m2": VOTE_VERIFIED, "m3": VOTE_VERIFIED})
    yield stub
    stub.close()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "PINEAL_JURY_LOCAL_URL",
        "PINEAL_JURY_LOCAL_MODELS",
        "PINEAL_JURY_QUORUM",
        "LOCAL_LLM_URL",
        "LOCAL_LLM_MODEL",
        "ENABLE_LOCAL_JURY",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def _configure(monkeypatch, stub: _LocalLLM, models: str = "m1,m2,m3"):
    monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", stub.url)
    monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", models)


def _run(cap_id, ctx, state):
    runner = CapabilityRunner(registry=bootstrap())
    return asyncio.run(runner.run(cap_id, ctx, state=state))


def _unlocked_state(**flags) -> PolicyState:
    return PolicyState(vault_locked=False, rate_ok=True, enabled_flags=dict(flags))


class TestGates:
    def test_registered_on_the_spine(self):
        registry = bootstrap()
        cap = registry.get(CAP_ID)
        assert sorted(cap.gates) == ["ENABLE_LOCAL_JURY", "vault"]

    def test_vault_gate_blocks_even_when_flag_open(self, monkeypatch, local_llm):
        _configure(monkeypatch, local_llm)
        result = _run(
            CAP_ID,
            CapabilityContext(subject=CLAIM, params={"evidence": EVIDENCE}),
            PolicyState(vault_locked=True, rate_ok=True, enabled_flags={"ENABLE_LOCAL_JURY": True}),
        )
        assert result.denied_by == "vault"
        assert result.items == ()

    def test_disabled_flag_blocks(self, monkeypatch, local_llm):
        _configure(monkeypatch, local_llm)
        result = _run(
            CAP_ID,
            CapabilityContext(subject=CLAIM, params={"evidence": EVIDENCE}),
            _unlocked_state(ENABLE_LOCAL_JURY=False),
        )
        assert result.denied_by == "ENABLE_LOCAL_JURY"
        assert result.unavailable_reason == "policy:gate_disabled"

    def test_availability_is_honest_without_models(self):
        registry = bootstrap()
        availability = registry.get(CAP_ID).availability()
        assert availability.available is False
        assert availability.reason == "no_local_models"


class TestVerdictContract:
    def test_consensus_produces_inference_evidence(self, monkeypatch, local_llm):
        _configure(monkeypatch, local_llm)
        result = _run(
            CAP_ID,
            CapabilityContext(subject=CLAIM, params={"evidence": EVIDENCE}),
            _unlocked_state(ENABLE_LOCAL_JURY=True),
        )
        assert result.available is True
        assert result.ok is True
        item = result.items[0]
        assert item.epistemic_type == "inference"  # model yargısı ≠ gözlem
        assert item.source_engine == "local_jury"
        assert "DOĞRULANDI" in item.content
        assert item.confidence == pytest.approx(0.8)
        assert item.scope["rule"] == "oy_birligi"
        assert item.scope["models"] == ["m1", "m2", "m3"]

    def test_non_consensus_produces_no_claim(self, monkeypatch, local_llm):
        local_llm.votes = {"m1": VOTE_VERIFIED, "m2": VOTE_FALSE, "m3": VOTE_VERIFIED}
        _configure(monkeypatch, local_llm, "m1,m2,m3")
        monkeypatch.setenv("PINEAL_JURY_QUORUM", "3")
        result = _run(
            CAP_ID,
            CapabilityContext(subject=CLAIM, params={"evidence": EVIDENCE}),
            _unlocked_state(ENABLE_LOCAL_JURY=True),
        )
        assert result.available is True
        assert result.items == ()          # konsensüs yok → İDDİA YOK
        assert result.ok is False
        assert result.notes["rule"] == "cokluk"
        assert result.notes["consensus"] is False
        assert result.notes["tally"] == {VOTE_VERIFIED: 2, VOTE_FALSE: 1}

    def test_seat_detail_is_not_hidden(self, monkeypatch, local_llm):
        local_llm.votes = {"m1": VOTE_VERIFIED, "m2": "SAÇMA", "m3": VOTE_VERIFIED}
        _configure(monkeypatch, local_llm)
        result = _run(
            CAP_ID,
            CapabilityContext(subject=CLAIM, params={"evidence": EVIDENCE}),
            _unlocked_state(ENABLE_LOCAL_JURY=True),
        )
        seats = {seat["model"]: seat for seat in result.notes["seats"]}
        assert seats["m2"]["error"] == "sozluk_disi"
        assert result.notes["seat_errors"] == {"m2": "sozluk_disi"}

    def test_engine_missing_no_verdict(self, monkeypatch):
        result = _run(
            CAP_ID,
            CapabilityContext(subject=CLAIM, params={"evidence": EVIDENCE}),
            _unlocked_state(ENABLE_LOCAL_JURY=True),
        )
        assert result.available is False
        assert result.unavailable_reason == "no_local_models"


class TestExportSurfaces:
    def test_mcp_tool_appears_from_registry(self):
        tools = {tool["title"]: tool for tool in build_tools(bootstrap())}
        assert CAP_ID in tools
        assert tools[CAP_ID]["name"] == "verifier_jury_local"
        assert tools[CAP_ID]["annotations"]["readOnlyHint"] is True

    def test_status_row_exposes_gate_state(self):
        from agent_core.capabilities.policy import PolicyKernel

        rows = {row["id"]: row for row in bootstrap().status(
            _unlocked_state(ENABLE_LOCAL_JURY=False), kernel=PolicyKernel()
        )}
        row = rows[CAP_ID]
        assert row["policy_allowed"] is False
        assert row["policy_gate"] == "ENABLE_LOCAL_JURY"
        assert row["available"] is False  # model tanımlı değil → dürüst "hazır değil"
