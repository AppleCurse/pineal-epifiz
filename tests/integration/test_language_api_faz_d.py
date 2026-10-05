"""FAZ D · D4 — dil uçları uçtan uca: omurga + kasa + dürüst sonuçlar.

Kilitlenen iddialar:
    * `/api/language/detect` ölçer: tr doğru döner; sinyal yoksa `unknown`
      + sebep döner (etiket UYDURULMAZ); kasa kilitliyken TESPİT BİLE koşamaz.
    * `/api/language/translate` ses/dinleme ile aynı kurala bağlıdır: kapı
      kapalıyken ve motor yokken çeviri ÜRETİLMEZ; YEREL uç çalışır ve
      kaynak dili raporlar; UZAK uç reddedilir.
    * `/api/language/status` gerçek durumu gösterir (uydurma uygunluk yok).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from backend import api

TR_TEXT = (
    "Merhaba, bugün hava çok güzel ve ben dışarı çıkmak istiyorum. "
    "Ama önce işlerimi bitirmem gerekiyor çünkü yarın için hazırlık yapmalıyım."
)


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _open_vault(client):
    """Kasa interlock'u (Tüzük Md.4): test odasının mandalı açılır."""
    client.get("/api/telemetry?client_id=lsp")
    room = api.get_room("lsp")
    room["vault"]["or_key"] = True
    yield
    room["vault"].pop("or_key", None)


@pytest.fixture(autouse=True)
def _clean_language_state():
    from agent_core.services import language

    language.reset_last_finding()
    yield
    language.reset_last_finding()


class TestStatus:
    def test_status_reports_real_state(self, client, monkeypatch):
        # Hermetik: makinede `trans` olsa bile motor yokluğu sınanır.
        monkeypatch.delenv("PINEAL_TRANSLATE_URL", raising=False)
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", "pineal-olmayan-komut")
        payload = client.get("/api/language/status").json()
        assert payload["detect"]["available"] is True
        assert payload["detect"]["method"] == "deterministic_local"
        assert payload["translate"]["gate"] == "ENABLE_LOCAL_TRANSLATE"
        assert payload["translate"]["available"] is False  # motor yok: dürüst
        assert payload["last"] is None  # hiç ölçüm yapılmadı


class TestDetect:
    def test_detect_measures_turkish(self, client):
        payload = client.post(
            "/api/language/detect", json={"text": TR_TEXT, "client_id": "lsp"}
        ).json()
        assert payload["available"] is True
        assert payload["language"] == "tr"
        assert payload["confidence"] >= 0.85
        assert payload["script"] == "latin"

    def test_detect_without_signal_returns_unknown_not_label(self, client):
        payload = client.post(
            "/api/language/detect",
            json={"text": "qw zx as df qwer zxcv qwert zxcvb", "client_id": "lsp"},
        ).json()
        assert payload["available"] is True
        assert payload["language"] == "unknown"
        assert payload["detect_reason"] == "no_signal"
        assert payload["confidence"] == 0.0

    def test_detect_denied_when_vault_locked(self, client):
        room = api.get_room("lsp")
        room["vault"].pop("or_key", None)  # kasa KİLİTLİ
        payload = client.post(
            "/api/language/detect", json={"text": TR_TEXT, "client_id": "lsp"}
        ).json()
        assert payload["denied_by"] == "vault"
        assert payload["language"] == ""  # kilitliyken tespit de yok


class TestTranslate:
    def test_translate_without_engine_produces_nothing(self, client, monkeypatch):
        monkeypatch.delenv("ENABLE_LOCAL_TRANSLATE", raising=False)
        monkeypatch.delenv("PINEAL_TRANSLATE_URL", raising=False)
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", "pineal-olmayan-komut")
        payload = client.post(
            "/api/language/translate",
            json={"text": TR_TEXT, "target": "en", "client_id": "lsp"},
        ).json()
        assert payload["available"] is False
        assert payload["text"] == ""  # uydurma çeviri YOK
        assert payload["denied_by"] or payload["reason"]

    def test_translate_gate_closed_even_with_engine(self, client, monkeypatch):
        monkeypatch.delenv("ENABLE_LOCAL_TRANSLATE", raising=False)
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "http://127.0.0.1:1/t")
        payload = client.post(
            "/api/language/translate",
            json={"text": TR_TEXT, "target": "en", "client_id": "lsp"},
        ).json()
        assert payload["available"] is False
        assert payload["denied_by"] == "ENABLE_LOCAL_TRANSLATE"

    def test_translate_with_local_endpoint(self, client, monkeypatch):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server sözleşmesi
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                out = json.dumps(
                    {"text": "Hello, the weather is very nice today.", "source": body.get("source")}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv(
            "PINEAL_TRANSLATE_URL", f"http://127.0.0.1:{server.server_port}/translate"
        )
        try:
            payload = client.post(
                "/api/language/translate",
                json={"text": TR_TEXT, "target": "en", "client_id": "lsp"},
            ).json()
            assert payload["available"] is True, payload
            assert payload["text"].startswith("Hello")
            assert payload["source_language"] == "tr"  # hangi dilden: gizlenmez
            assert payload["target_language"] == "en"
            assert payload["engine"] == "local_endpoint"
        finally:
            server.shutdown()

    def test_remote_endpoint_rejected(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "https://uzak-cevirici.example.com/t")
        payload = client.post(
            "/api/language/translate",
            json={"text": TR_TEXT, "target": "en", "client_id": "lsp"},
        ).json()
        assert payload["available"] is False
        assert payload["reason"] == "non_local_endpoint"
        assert payload["text"] == ""  # metin makineden çıkmadı, çeviri yok

    def test_translate_denied_when_vault_locked(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "http://127.0.0.1:1/t")
        room = api.get_room("lsp")
        room["vault"].pop("or_key", None)
        payload = client.post(
            "/api/language/translate",
            json={"text": TR_TEXT, "target": "en", "client_id": "lsp"},
        ).json()
        assert payload["denied_by"] == "vault"
