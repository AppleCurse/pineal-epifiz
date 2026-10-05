"""FAZ C · C2 — Ses uçtan uca: gerçek YEREL motor + WS konuşma durumu.

Kilitlenen iddia: Aspasia konuşur; ses YERELDE üretilir (uç 127.0.0.1),
konuşma durumu WebSocket'ten UI'a akar, araya girme (`stop`) durumu keser.
Motor yoksa uç 200 döner ama `available:false` yazar — uydurma ses yok.
"""

from __future__ import annotations

import asyncio
import json
import math
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from backend import api


def _wav(seconds: float = 1.5, rate: int = 8000) -> bytes:
    samples = int(rate * seconds)
    data = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 220 * i / rate)))
        for i in range(samples)
    )
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


@pytest.fixture(autouse=True)
def _open_vault(client):
    """Kasa interlock'u (Tüzük Md.4): test odasında kasa AÇIK olmalı.

    Kilitli kasa hiçbir yeteneğe izin vermez — ses de dâhil. Burada gerçek
    anahtar malzemesi taklit EDİLMEZ, yalnız odanın mandalı açılır (aynı
    desen: /api/vault ile operatörün açtığı kasa).

    DİKKAT: oda ÖNCEDEN (portal döngüsünde) kurulmalı; aksi hâlde WebSocket
    gönderici görevi yaratılmaz ve çerçeveler hiç ulaşmaz.
    """
    client.get("/api/telemetry?client_id=spx")
    room = api.get_room("spx")
    room["vault"]["or_key"] = True
    yield
    room["vault"].pop("or_key", None)


@pytest.fixture()
def local_tts(monkeypatch, tmp_path):
    """Gerçek bir YEREL TTS sunucusu (ephemeral port) + açılmış kapı."""
    audio = _wav(1.5)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server sözleşmesi
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)

        def log_message(self, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("PINEAL_TTS_URL", f"http://127.0.0.1:{server.server_port}/tts")
    monkeypatch.setenv("ENABLE_LOCAL_TTS", "true")
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


def test_status_reports_engine_state(client, local_tts):
    payload = client.get("/api/speech/status").json()
    assert payload["available"] is True
    assert payload["engine"] == "local_endpoint"
    assert payload["gate_enabled"] is True
    assert payload["state"] == "idle"


def test_say_synthesizes_and_serves_audio(client, local_tts):
    result = client.post(
        "/api/speech/say", json={"text": "Mösyö, görev tamamlandı.", "client_id": "spx"}
    ).json()
    assert result["available"] is True, result.get("reason")
    assert result["engine"] == "local_endpoint"
    assert result["duration_ms"] == 1500
    assert result["url"].startswith("/api/speech/audio/")

    audio = client.get(result["url"])
    assert audio.status_code == 200
    assert audio.content[:4] == b"RIFF"


def test_say_refuses_when_gate_is_closed(client, monkeypatch, tmp_path):
    monkeypatch.delenv("ENABLE_LOCAL_TTS", raising=False)
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    result = client.post(
        "/api/speech/say", json={"text": "Mösyö.", "client_id": "spx"}
    ).json()
    assert result["available"] is False
    assert "gate_disabled" in result["reason"]


def test_remote_endpoint_is_never_called(client, monkeypatch, tmp_path):
    """Uzak uç: yetenek reddeder, metin makineden çıkmaz."""
    monkeypatch.setenv("ENABLE_LOCAL_TTS", "true")
    monkeypatch.setenv("PINEAL_TTS_URL", "https://tts.example.com/speak")
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    result = client.post(
        "/api/speech/say", json={"text": "gizli metin", "client_id": "spx"}
    ).json()
    assert result["available"] is False
    assert "non_local_endpoint" in result["reason"]


def test_speaking_state_reaches_the_ui_over_websocket(client, local_tts):
    with client.websocket_connect("/ws/spx") as ws:
        result = client.post(
            "/api/speech/say", json={"text": "Mösyö, dinliyorum.", "client_id": "spx"}
        ).json()
        assert result["available"] is True
        frame = json.loads(ws.receive_text())
        # İlk çerçeveler log olabilir; konuşma çerçevesini bulana kadar oku.
        while frame.get("type") != "speech":
            frame = json.loads(ws.receive_text())
    assert frame["state"] == "speaking"
    assert frame["engine"] == "local_endpoint"
    assert frame["duration_ms"] == 1500


def test_speech_returns_to_idle_after_the_audio_duration(client, local_tts, monkeypatch):
    from agent_core.services import speech

    client.post("/api/speech/say", json={"text": "kısa", "client_id": "spx"}).json()
    assert client.get("/api/speech/status").json()["state"] == "speaking"
    asyncio.run(api._speech_finished("spx", 0.01))
    assert client.get("/api/speech/status").json()["state"] == "idle"


def test_stop_interrupts_the_speech(client, local_tts):
    client.post("/api/speech/say", json={"text": "uzun cümle", "client_id": "spx"}).json()
    assert client.get("/api/speech/status").json()["state"] == "speaking"
    payload = client.post("/api/speech/stop?client_id=spx").json()
    assert payload["status"] == "stopped"
    assert payload["state"] == "idle"


def test_locked_vault_blocks_speech(client, local_tts, monkeypatch):
    """Kasa kilitliyken motor hazır olsa bile ses ÜRETİLMEZ (Tüzük Md.4)."""
    api.get_room("spx")["vault"].pop("or_key", None)
    result = client.post(
        "/api/speech/say", json={"text": "Mösyö.", "client_id": "spx"}
    ).json()
    assert result["available"] is False
    assert result["reason"] == "policy:vault_locked"
