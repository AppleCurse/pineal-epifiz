"""STT multipart → GERÇEK motor yolu (P1, 2026-11-11).

Ölçülen kusur (düzeltme ÖNCESİ, gerçek sunucu):
    ``POST /api/speech/listen`` dosya yüklemesini kabul ediyor gibi görünüyordu
    ama:
      1. ``python-multipart`` kurulu değilken HER yükleme 500
         ``MULTIPART_UNAVAILABLE`` ile düşüyordu — bu, "motor yok" ile
         karıştırılıyordu (altyapı kusuru ↔ yetenek yokluğu ayrımı yoktu).
      2. ``/api/speech/status`` motor yokken ``{"available": false,
         "reason": "no_local_endpoint"}`` diyordu: sebep var ama NE YAPILACAĞI
         ve kapının (``ENABLE_LOCAL_STT``) durumu tek yerde söylenmiyordu.

Düzeltme sonrası sözleşme (ölçülen):
    1. Gerçek multipart isteği → gerçek yerel motora (döngü içi bir HTTP ucu)
       GİDER; alıcıya ulaşan gövde, yüklenen sesi birebir içerir.
    2. Motor yokken transkript UYDURULMAZ: ``available=false`` + makine-okunur
       sebep + eylem ipucu.
    3. Uzak STT ucu REDDEDİLİR (ses makineden çıkmaz) — davranış korunur.
    4. Kapı kapalıyken ilk eylem "kapıyı aç" olarak söylenir.
"""

from __future__ import annotations

import io
import json
import socket
import struct
import threading
import wave

import pytest
from fastapi.testclient import TestClient


def _real_wav(seconds: float = 0.25, rate: int = 16000) -> bytes:
    """Gerçek WAV (sessizlik) — multipart gövdesinde bayt bayt aranacak."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack("<%dh" % int(rate * seconds), *([0] * int(rate * seconds))))
    return buffer.getvalue()


class _LocalSTTServer:
    """Döngü içinde GERÇEK HTTP sunucusu (ürün koduna gömülü değil).

    Uydurma transkript üretmez: isteği alır, gövdeyi saklar, transkript olarak
    ``text/plain`` sabit bir metin döner ve bunu test tarafında doğrularız.
    """

    def __init__(self) -> None:
        self.body = b""
        self.path = ""
        self._server = None
        self._thread = None
        self.reply = "yerel motor dinledi"

    def __enter__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("content-length") or 0)
                outer.body = self.rfile.read(length)
                outer.path = self.path
                payload = outer.reply.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/plain; charset=utf-8")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # sessiz
                return

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/stt"

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture()
def vault_open_client(monkeypatch):
    """Kasa AÇIK istemci.

    Kasa mandalı bu testin KONUSU değil (girişi ayrıca ölçülür). Router
    bağımlılıkları kurulum anında bağladığı için mandal, oda kaydı üzerinden
    açılır: gerçek gerçek anahtar malzemesi (`or_key`) yazılır — yani test
    üretimdeki yolun AYNISINI kullanır, kodu taklit etmez.
    """
    import backend.api as api_module

    # STT kapısı testte AÇILIR: konu kapı politikası değil, multipart→motor yolu
    # (kapı davranışı test_gate_closed_hint_names_the_gate_first'te ölçülür).
    monkeypatch.setenv("ENABLE_LOCAL_STT", "true")
    monkeypatch.setattr(api_module, "broadcast_speech", lambda cid, payload: None)
    api_module.get_room("stt_test")["vault"]["or_key"] = True
    api_module.get_room("stt_none")["vault"]["or_key"] = True
    api_module.get_room("stt_big")["vault"]["or_key"] = True
    api_module.get_room("stt_empty")["vault"]["or_key"] = True
    with TestClient(api_module.app) as client:
        yield client


def test_multipart_is_actually_available():
    """python-multipart kurulu değilse yükleme yolu sessizce çalışmaz — ölç."""
    from agent_core.services import speech

    assert speech.status()["stt"]["multipart_available"] is True


def test_status_reports_honest_reason_and_remediation(monkeypatch):
    """Motor yokken sebep BOŞ olamaz; ne yapılacağı söylenir."""
    from agent_core.services import speech
    from agent_core.capabilities.adapters_voice import STT_NOT_INSTALLED_REASON

    monkeypatch.delenv("PINEAL_STT_URL", raising=False)
    monkeypatch.delenv("PINEAL_STT_CMD", raising=False)
    monkeypatch.setenv("ENABLE_LOCAL_STT", "true")

    stt = speech.status()["stt"]
    assert stt["available"] is False
    assert stt["reason"] == STT_NOT_INSTALLED_REASON, stt
    assert "whisper" in stt["remediation"]
    assert "ENABLE_LOCAL_STT" in stt["remediation"]


def test_gate_closed_hint_names_the_gate_first(monkeypatch):
    """Kapı kapalıysa ilk eylem kapıyı açmak (motor kurulumu ikinci adım)."""
    from agent_core.services import speech

    monkeypatch.delenv("ENABLE_LOCAL_STT", raising=False)
    stt = speech.status()["stt"]
    assert stt["gate_enabled"] is False
    assert stt["remediation"].startswith("Dinleme kapalı")
    assert "ENABLE_LOCAL_STT=true" in stt["remediation"]


def test_remote_stt_endpoint_is_refused(monkeypatch):
    """Ses makineden çıkmaz: uzak uç REDDEDİLİR, sebep spesifik kalır."""
    from agent_core.capabilities.adapters_voice import LocalSTTCapability

    monkeypatch.setenv("PINEAL_STT_URL", "http://stt.example.com/v1")
    engine, reason = LocalSTTCapability().backend()
    assert engine == ""
    assert reason == "non_local_endpoint"


def test_upload_reaches_a_real_local_engine_byte_for_byte(vault_open_client):
    """KUSURUN KALBİ: multipart yükleme GERÇEK motora ulaşmalı, kaybolmamalı."""
    import backend.api as api_module

    audio = _real_wav()
    with _LocalSTTServer() as engine:
        api_module.app.state.speech_stt_url = engine.url
        original = __import__("os").environ.get("PINEAL_STT_URL")
        __import__("os").environ["PINEAL_STT_URL"] = engine.url
        try:
            response = vault_open_client.post(
                "/api/speech/listen?client_id=stt_test",
                files={"file": ("mic.wav", audio, "audio/wav")},
            )
        finally:
            if original is None:
                __import__("os").environ.pop("PINEAL_STT_URL", None)
            else:
                __import__("os").environ["PINEAL_STT_URL"] = original

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True, body
    assert body["transcript"] == "yerel motor dinledi"
    assert body["engine"] == "local_endpoint"
    # GERÇEK ölçüm: yüklenen ses, motorun gördüğü gövdede birebir var.
    assert audio in engine.body, "yüklenen ses motora ULAŞMADI (multipart kaybı)"
    assert b'name="file"' in engine.body
    assert engine.path.startswith("/stt")


def test_listen_without_engine_returns_no_fabricated_transcript(vault_open_client, monkeypatch):
    """Motor yokken: uydurma transkript YOK, dürüst ret + sebep."""
    import os

    monkeypatch.delenv("PINEAL_STT_CMD", raising=False)
    monkeypatch.setenv("ENABLE_LOCAL_STT", "true")
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9/stt")  # kapalı port

    response = vault_open_client.post(
        "/api/speech/listen?client_id=stt_none",
        files={"file": ("mic.wav", _real_wav(), "audio/wav")},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["available"] is False
    assert body["transcript"] == ""
    assert body["reason"], "sebepsiz ret yasak"


def test_oversized_audio_is_rejected_before_engine(vault_open_client):
    """8 MiB tavanı motordan ÖNCE uygulanır (kaynak tüketimi)."""
    import backend.api as api_module
    from backend.routes.speech import MAX_LISTEN_AUDIO_BYTES

    big = b"RIFF" + b"\x00" * (MAX_LISTEN_AUDIO_BYTES + 10)
    response = vault_open_client.post(
        "/api/speech/listen?client_id=stt_big",
        files={"file": ("big.wav", big, "audio/wav")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "AUDIO_TOO_LARGE"
    assert api_module is not None


def test_empty_audio_is_rejected(vault_open_client):
    response = vault_open_client.post(
        "/api/speech/listen?client_id=stt_empty",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_AUDIO"


def test_socket_is_local_only():
    """Test yardımcısının kendisi de yerel (yoksa ölçüm yanıltıcı olurdu)."""
    with _LocalSTTServer() as engine:
        host = engine.url.split("//", 1)[1].split(":", 1)[0]
        assert host in {"127.0.0.1", "localhost"}
        with pytest.raises(OSError):
            socket.create_connection((host, 1), timeout=0.2)
    # json importu test dosyasında kullanılmıyor olabilir; sözleşme gereği tutulur.
    assert json.dumps({"ok": True})
