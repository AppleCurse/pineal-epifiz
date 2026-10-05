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
def local_stt(monkeypatch, tmp_path):
    """Gerçek bir YEREL STT sunucusu (ephemeral port) + açılmış kapı."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server sözleşmesi
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps({"text": "Mösyö, bu hedefin son iki haftasını göster."}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("PINEAL_STT_URL", f"http://127.0.0.1:{server.server_port}/stt")
    monkeypatch.setenv("ENABLE_LOCAL_STT", "true")
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

    client.post("/api/speech/say", json={"text": "kısa", "client_id": "spx"}).json()
    assert client.get("/api/speech/status").json()["state"] == "speaking"
    asyncio.run(api._speech_finished("spx", 0.01))
    assert client.get("/api/speech/status").json()["state"] == "idle"


def test_stop_interrupts_the_speech(client, local_tts):
    """[FAZ C · C3] Konuşurken durdurmak = ARAYA GİRME: `interrupted` döner."""
    client.post("/api/speech/say", json={"text": "uzun cümle", "client_id": "spx"}).json()
    assert client.get("/api/speech/status").json()["state"] == "speaking"
    payload = client.post("/api/speech/stop?client_id=spx").json()
    assert payload["status"] == "interrupted"
    assert payload["state"] == "idle"


def test_locked_vault_blocks_speech(client, local_tts, monkeypatch):
    """Kasa kilitliyken motor hazır olsa bile ses ÜRETİLMEZ (Tüzük Md.4)."""
    api.get_room("spx")["vault"].pop("or_key", None)
    result = client.post(
        "/api/speech/say", json={"text": "Mösyö.", "client_id": "spx"}
    ).json()
    assert result["available"] is False
    assert result["reason"] == "policy:vault_locked"


# =====================================================================
# FAZ C · C3 — DİNLEYEN GÖZ (mikrofon -> yerel STT -> WS durumu)
# =====================================================================
def test_listen_transcribes_with_local_engine(client, local_stt):
    result = client.post(
        "/api/speech/listen?client_id=spx",
        files={"file": ("mic.webm", b"RIFFfake-audio", "audio/webm")},
    ).json()
    assert result["available"] is True, result.get("reason")
    assert result["transcript"].startswith("Mösyö")
    assert result["engine"] == "local_endpoint"


def test_listen_broadcasts_listening_state(client, local_stt):
    with client.websocket_connect("/ws/spx") as ws:
        client.post(
            "/api/speech/listen?client_id=spx",
            files={"file": ("mic.webm", b"RIFFfake-audio", "audio/webm")},
        )
        frames = []
        for _ in range(40):
            frame = json.loads(ws.receive_text())
            if frame.get("type") == "speech":
                frames.append(frame.get("state"))
                if "listening" in frames and frames[-1] == "idle":
                    break
    assert "listening" in frames, frames


def test_listen_rejects_missing_audio(client, local_stt):
    response = client.post("/api/speech/listen?client_id=spx")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NO_AUDIO"


def test_listen_without_engine_invents_no_transcript(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_LOCAL_STT", "true")
    monkeypatch.delenv("PINEAL_STT_URL", raising=False)
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    result = client.post(
        "/api/speech/listen?client_id=spx",
        files={"file": ("mic.webm", b"RIFFfake-audio", "audio/webm")},
    ).json()
    assert result["available"] is False
    assert result["transcript"] == ""
    assert result["reason"]


def test_interrupt_while_speaking_cuts_the_speech(client, local_tts):
    client.post("/api/speech/say", json={"text": "uzun konuşma", "client_id": "spx"}).json()
    assert client.get("/api/speech/status").json()["state"] == "speaking"
    payload = client.post("/api/speech/stop?client_id=spx").json()
    assert payload["status"] == "interrupted"
    status = client.get("/api/speech/status").json()
    assert status["state"] == "idle"
    assert status["interrupted"] is True
    assert status["interrupted_from"] == "speaking"


def test_status_lists_known_conversation_states(client):
    payload = client.get("/api/speech/status").json()
    assert "listening" in payload["known_states"]
    assert "interrupted" in payload["known_states"]
    assert "speaking" in payload["known_states"]


# =====================================================================
# FAZ C · C4 — SESLİ RAPOR (bulunanı söyle)
# =====================================================================
REPORT_PAYLOAD = {
    "status": "completed",
    "target_profile": {"username": "salim.gumus"},
    "evidence_chain": [{"agent": "a"}, {"agent": "b"}],
    "runs": {"a": {"status": "completed", "confidence": 0.8}, "b": {"status": "failed"}},
    "changes": {"available": True, "added": [1, 2], "removed": [], "changed": [3]},
}


def test_report_endpoint_speaks_the_findings(client, local_tts):
    payload = client.post(
        "/api/speech/report",
        json={"client_id": "spx", "report": REPORT_PAYLOAD},
    ).json()
    assert payload["available"] is True, payload.get("reason")
    assert "Hedef salim.gumus." in payload["script"]
    assert payload["sections"][0] == "target"
    assert payload["url"].endswith(".wav")


def test_report_endpoint_broadcasts_speaking_state(client, local_tts):
    with client.websocket_connect("/ws/spx") as ws:
        client.post("/api/speech/report", json={"client_id": "spx", "report": REPORT_PAYLOAD})
        frame = json.loads(ws.receive_text())
        while frame.get("type") != "speech":
            frame = json.loads(ws.receive_text())
    assert frame["state"] == "speaking"
    assert frame["script"].startswith("Hedef")


def test_report_without_engine_keeps_the_text_but_no_audio(client, monkeypatch, tmp_path):
    monkeypatch.delenv("ENABLE_LOCAL_TTS", raising=False)
    monkeypatch.delenv("PINEAL_TTS_URL", raising=False)
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    payload = client.post(
        "/api/speech/report", json={"client_id": "spx", "report": REPORT_PAYLOAD}
    ).json()
    assert payload["available"] is False
    assert payload["url"] == ""
    assert "Hedef salim.gumus." in payload["script"]  # metin gizlenmez


def test_report_endpoint_invents_no_sentence_from_empty_report(client, local_tts):
    payload = client.post("/api/speech/report", json={"client_id": "spx", "report": {}}).json()
    assert payload["available"] is False
    assert payload["script"] == ""


def test_report_status_exposes_the_report_capability(client):
    payload = client.get("/api/speech/status").json()
    assert payload["report"]["capability_id"] == "voice.report.script"
    assert payload["report"]["available"] is True
