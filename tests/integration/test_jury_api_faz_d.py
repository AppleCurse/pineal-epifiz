"""FAZ D · D2 — yerel jüri uçları: kapılar, dürüst kural, veri makineden çıkmaz.

Kilitlenen iddialar:
    * `/api/jury/status` gerçek durumu döner: model yoksa ``available: false``
      ve sebep; uç uzaksa ret; tek modelde "bağımsız koltuk" DENMEZ.
    * `/api/jury/vote` omurgadan geçer: kasa kapalıysa ve kapı kapalıyken
      oylama KOŞMAZ; konsensüs varsa karar, yoksa ``consensus: false`` +
      kural döner (karar uydurulmaz).
    * Koltuk dökümü ve hataları yanıtta görünür (sessiz yutma yok).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from backend import api

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
                vote = outer.votes.get(request.get("model", ""), "DOĞRULANDI")
                content = json.dumps({"vote": vote, "confidence": 0.6, "reason": "t"})
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
def client():
    with TestClient(api.app) as test_client:
        yield test_client


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


@pytest.fixture()
def vault(client):
    client.get("/api/telemetry?client_id=jury")
    room = api.get_room("jury")
    yield room["vault"]
    room["vault"].pop("or_key", None)


@pytest.fixture()
def local_llm():
    stub = _LocalLLM({"m1": "DOĞRULANDI", "m2": "DOĞRULANDI", "m3": "DOĞRULANDI"})
    yield stub
    stub.close()


class TestStatus:
    def test_status_is_honest_without_models(self, client):
        payload = client.get("/api/jury/status").json()
        assert payload["available"] is False
        assert payload["reason"] == "no_local_models"
        assert payload["gate"] == "ENABLE_LOCAL_JURY"

    def test_remote_endpoint_is_rejected(self, client, monkeypatch):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2")
        payload = client.get("/api/jury/status").json()
        assert payload["available"] is False
        assert payload["reason"] == "non_local_endpoint"
        assert payload["endpoint"] is None

    def test_single_model_is_not_independent(self, client, monkeypatch, local_llm):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", local_llm.url)
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1")
        payload = client.get("/api/jury/status").json()
        assert payload["available"] is True
        assert payload["independent_seats"] is False
        assert "konsensüs" in payload["note"]


class TestVote:
    def test_vault_locked_blocks_the_vote(self, client, monkeypatch, local_llm):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", local_llm.url)
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2,m3")
        monkeypatch.setenv("ENABLE_LOCAL_JURY", "1")
        api.get_room("jury")["vault"].pop("or_key", None)
        payload = client.post(
            "/api/jury/vote",
            json={"claim": CLAIM, "evidence": EVIDENCE, "client_id": "jury"},
        ).json()
        assert payload["denied_by"] == "vault"
        assert payload["consensus"] is False
        assert payload["seats"] == []

    def test_disabled_gate_blocks_the_vote(self, client, vault, monkeypatch, local_llm):
        vault["or_key"] = True
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", local_llm.url)
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2,m3")
        payload = client.post(
            "/api/jury/vote",
            json={"claim": CLAIM, "evidence": EVIDENCE, "client_id": "jury"},
        ).json()
        assert payload["denied_by"] == "ENABLE_LOCAL_JURY"
        assert payload["consensus"] is False

    def test_unanimous_vote_is_consensus(self, client, vault, monkeypatch, local_llm):
        vault["or_key"] = True
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", local_llm.url)
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2,m3")
        monkeypatch.setenv("ENABLE_LOCAL_JURY", "1")
        payload = client.post(
            "/api/jury/vote",
            json={"claim": CLAIM, "evidence": EVIDENCE, "client_id": "jury"},
        ).json()
        assert payload["available"] is True
        assert payload["consensus"] is True
        assert payload["verdict"] == "DOĞRULANDI"
        assert payload["rule"] == "oy_birligi"
        assert payload["counted"] == 3
        assert len(payload["evidence_ids"]) == 1
        assert {seat["model"] for seat in payload["seats"]} == {"m1", "m2", "m3"}

    def test_majority_with_dissent_is_consensus(self, client, vault, monkeypatch, local_llm):
        vault["or_key"] = True
        local_llm.votes = {"m1": "YALAN", "m2": "YALAN", "m3": "DOĞRULANDI"}
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", local_llm.url)
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2,m3")
        monkeypatch.setenv("ENABLE_LOCAL_JURY", "1")
        payload = client.post(
            "/api/jury/vote",
            json={"claim": CLAIM, "evidence": EVIDENCE, "client_id": "jury"},
        ).json()
        assert payload["verdict"] == "YALAN"
        assert payload["rule"] == "cokluk"
        assert payload["consensus"] is True
        assert payload["dissent"] == ["m3"]

    def test_tie_yields_no_decision(self, client, vault, monkeypatch, local_llm):
        vault["or_key"] = True
        local_llm.votes = {"m1": "DOĞRULANDI", "m2": "ÇELİŞKİLİ"}
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", local_llm.url)
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2")
        monkeypatch.setenv("ENABLE_LOCAL_JURY", "1")
        payload = client.post(
            "/api/jury/vote",
            json={"claim": CLAIM, "evidence": EVIDENCE, "client_id": "jury"},
        ).json()
        assert payload["verdict"] == "BİLİNMİYOR"
        assert payload["rule"] == "berabere"
        assert payload["consensus"] is False
        assert payload["evidence_ids"] == []

    def test_engine_missing_returns_honest_reason(self, client, vault, monkeypatch):
        vault["or_key"] = True
        monkeypatch.setenv("ENABLE_LOCAL_JURY", "1")
        payload = client.post(
            "/api/jury/vote",
            json={"claim": CLAIM, "evidence": EVIDENCE, "client_id": "jury"},
        ).json()
        assert payload["available"] is False
        assert payload["reason"] == "no_local_models"

    def test_rate_bucket_exists_for_jury(self):
        assert "jury" in api.RATE_LIMITS
