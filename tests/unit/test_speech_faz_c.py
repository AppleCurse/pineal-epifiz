"""FAZ C · C2 — YEREL SES (TTS) sözleşme testleri.

Kilitlenen iddialar:
1. Ses, Capability Spine'den geçer (registry + politika kapısı + kanıt) —
   paralel bir çağrı yolu YOKTUR.
2. **Ses makineden çıkmaz:** uç yalnız localhost olabilir; uzak uç REDDEDİLİR.
3. Motor yoksa uydurma ses ÜRETİLMEZ: `available:false` + makine-okunur sebep.
4. Seslendirme bir OLAYdır: kanıt zincirine yazar (motor + parmak izi + süre).
5. Konuşma durumu (`speaking`/`idle`/`denied`) TEK yerden yönetilir (C3'te
   dinleme ve araya girme aynı duruma bağlanacak).
"""

from __future__ import annotations

import asyncio
import os
import struct

import pytest

from agent_core.capabilities.adapters_voice import (
    LocalSTTCapability,
    LocalTTSCapability,
    _wav_duration_ms,
    speech_dir,
)
from agent_core.capabilities.base import CapabilityContext, CapabilityKind
from agent_core.capabilities.registry import bootstrap
from agent_core.services import speech


def _wav(seconds: float = 1.5, rate: int = 8000) -> bytes:
    import math

    samples = int(rate * seconds)
    data = b"".join(
        struct.pack("<h", int(12000 * ((i // 40) % 2 * 2 - 1))) for i in range(samples)
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


# ------------------------------------------------- 1 · omurgaya bağlılık
def test_tts_capability_is_registered_on_the_spine():
    registry = bootstrap()
    assert registry.has("voice.tts.local")
    capability = registry.get("voice.tts.local")
    assert capability.kind is CapabilityKind.RENDERER
    assert "ENABLE_LOCAL_TTS" in capability.gates


# ------------------------------------------------- 2 · ses makineden çıkmaz
def test_remote_endpoint_is_refused(monkeypatch):
    monkeypatch.setenv("PINEAL_TTS_URL", "https://tts.example.com/speak")
    capability = LocalTTSCapability()
    engine, reason = capability.backend()
    assert engine == ""
    assert reason == "non_local_endpoint"
    assert capability.availability().reason == "non_local_endpoint"


def test_local_endpoint_is_accepted(monkeypatch):
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")
    engine, reason = LocalTTSCapability().backend()
    assert engine == "local_endpoint"
    assert reason == ""


def test_no_engine_means_no_fake_voice(monkeypatch):
    monkeypatch.delenv("PINEAL_TTS_URL", raising=False)
    monkeypatch.delenv("PINEAL_PIPER_MODEL", raising=False)
    availability = LocalTTSCapability().availability()
    assert availability.available is False
    assert availability.reason in {"no_local_endpoint", "dependency_missing:piper"}


# ------------------------------------------------------ 3 · koşu sözleşmesi
def test_empty_text_produces_no_audio():
    result = asyncio.run(LocalTTSCapability().run(CapabilityContext(params={"text": "   "})))
    assert result.available is False
    assert result.unavailable_reason == "empty_text"
    assert result.items == ()


def test_synthesis_writes_audio_and_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")

    async def _fake(self, text, voice):  # yerel motorun yerine geçer
        return _wav(1.5), ""

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)

    result = asyncio.run(
        LocalTTSCapability().run(
            CapabilityContext(params={"text": "Mösyö, görev tamam.", "voice": "tr"})
        )
    )
    assert result.available is True
    assert result.ok is True, "kanıt üretilmedi"
    payload = result.payload
    assert payload["engine"] == "local_endpoint"
    assert payload["duration_ms"] == 1500, "süre WAV başlığından okunmadı"
    assert os.path.exists(payload["path"])
    item = result.items[0]
    assert item.scope["kind"] == "speech"
    assert item.scope["sha256"] == payload["sha256"]
    assert "Mösyö" in item.content


def test_failed_synthesis_produces_no_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")

    async def _fake(self, text, voice):
        return b"", "endpoint_status:503"

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(LocalTTSCapability().run(CapabilityContext(params={"text": "merhaba"})))
    assert result.available is False
    assert result.unavailable_reason == "endpoint_status:503"
    assert result.items == ()


def test_text_is_capped_and_control_chars_stripped(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")
    seen: dict = {}

    async def _fake(self, text, voice):
        seen["text"] = text
        return _wav(0.5), ""

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    asyncio.run(
        LocalTTSCapability().run(CapabilityContext(params={"text": "a\x00b " + "x" * 5000}))
    )
    assert "\x00" not in seen["text"]
    assert len(seen["text"]) <= 2000


def test_wav_duration_parsing():
    assert _wav_duration_ms(_wav(2.0)) == 2000
    assert _wav_duration_ms(b"not audio at all") is None
    assert _wav_duration_ms(b"") is None


# ----------------------------------------------------------- 4 · servis katmanı
def test_speak_denied_when_gate_closed(monkeypatch):
    monkeypatch.delenv("ENABLE_LOCAL_TTS", raising=False)
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")
    result = asyncio.run(speech.speak("Mösyö.", vault_locked=False))
    assert result.available is False
    assert result.state == "denied"
    assert "gate_disabled" in result.reason
    assert "uydurma ses yok" in result.machine_note


def test_speak_success_sets_speaking_state(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_LOCAL_TTS", "true")
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")

    async def _fake(self, text, voice):
        return _wav(1.0), ""

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(speech.speak("Mösyö, görev tamam.", vault_locked=False))
    assert result.available is True
    assert result.state == "speaking"
    assert result.url.startswith("/api/speech/audio/")
    assert speech.status()["state"] == "speaking"
    assert speech.status()["last"]["engine"] == "local_endpoint"


def test_stop_returns_to_idle(monkeypatch):
    speech.set_state("speaking")
    speech.stop()
    assert speech.status()["state"] == "idle"


def test_status_reports_engine_and_gate(monkeypatch):
    monkeypatch.delenv("PINEAL_TTS_URL", raising=False)
    monkeypatch.delenv("PINEAL_PIPER_MODEL", raising=False)
    monkeypatch.delenv("ENABLE_LOCAL_TTS", raising=False)
    payload = speech.status()
    assert payload["capability_id"] == "voice.tts.local"
    assert payload["gate_enabled"] is False
    assert payload["available"] is False
    assert payload["machine_note"].startswith("SES:")


def test_locked_vault_blocks_speech_even_with_engine(monkeypatch, tmp_path):
    """Tüzük Md.4: kasa kilitliyken motor hazır olsa bile ses ÜRETİLMEZ."""
    monkeypatch.setenv("ENABLE_LOCAL_TTS", "true")
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")

    async def _fake(self, text, voice):
        raise AssertionError("kasa kilitliyken motor ÇAĞRILMAMALI")

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(speech.speak("Mösyö.", vault_locked=True))
    assert result.available is False
    assert "vault" in result.reason
    assert result.state == "denied"


def test_unknown_vault_state_is_fail_closed(monkeypatch):
    """Durum bilinmiyorsa kasa KİLİTLİ sayılır (varsayılan True)."""
    monkeypatch.setenv("ENABLE_LOCAL_TTS", "true")
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")
    result = asyncio.run(speech.speak("Mösyö."))
    assert result.available is False
    assert result.reason == "policy:vault_locked"


# =====================================================================
# FAZ C · C3 — DİNLEYEN GÖZ (yerel STT + konuşma durumu)
# =====================================================================
def test_stt_capability_is_registered_on_the_spine():
    registry = bootstrap()
    assert registry.has("voice.stt.local")
    capability = registry.get("voice.stt.local")
    assert capability.kind is CapabilityKind.EXTRACTOR
    assert "ENABLE_LOCAL_STT" in capability.gates


def test_stt_refuses_remote_endpoint(monkeypatch):
    monkeypatch.setenv("PINEAL_STT_URL", "https://stt.example.com/transcribe")
    availability = LocalSTTCapability().availability()
    assert availability.available is False
    assert availability.reason in {"non_local_endpoint", "no_local_endpoint"}


def test_stt_rejects_empty_audio():
    result = asyncio.run(LocalSTTCapability().run(CapabilityContext(params={"audio": b""})))
    assert result.available is False
    assert result.unavailable_reason == "empty_audio"


def test_stt_rejects_oversized_audio(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9911/stt")
    result = asyncio.run(
        LocalSTTCapability().run(CapabilityContext(params={"audio": b"x" * (8 * 1024 * 1024 + 1)}))
    )
    assert result.available is False
    assert result.unavailable_reason == "audio_too_large"


def test_stt_transcribes_and_writes_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9911/stt")

    async def _fake(self, audio_path):
        return "Mösyö, bu hedefin son iki haftasını göster.", ""

    monkeypatch.setattr(LocalSTTCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(
        LocalSTTCapability().run(CapabilityContext(params={"audio": b"RIFFfake", "suffix": ".wav"}))
    )
    assert result.available is True
    assert result.payload["transcript"].startswith("Mösyö")
    assert result.items[0].scope["kind"] == "transcript"
    assert result.items[0].content.startswith("Mösyö")


def test_stt_failure_invents_no_transcript(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9911/stt")

    async def _fake(self, audio_path):
        return "", "endpoint_status:500"

    monkeypatch.setattr(LocalSTTCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(LocalSTTCapability().run(CapabilityContext(params={"audio": b"RIFFfake"})))
    assert result.available is False
    assert result.unavailable_reason == "endpoint_status:500"
    assert result.items == ()


def test_listen_denied_when_gate_closed(monkeypatch):
    monkeypatch.delenv("ENABLE_LOCAL_STT", raising=False)
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9911/stt")
    result = asyncio.run(speech.listen(b"RIFFfake", vault_locked=False))
    assert result.available is False
    assert result.state == "denied"
    assert "gate_disabled" in result.reason
    assert "uydurma transkript yok" in result.machine_note


def test_listen_success_returns_transcript(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_LOCAL_STT", "true")
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9911/stt")

    async def _fake(self, audio_path):
        return "görev tamam mı", ""

    monkeypatch.setattr(LocalSTTCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(speech.listen(b"RIFFfake", vault_locked=False))
    assert result.available is True
    assert result.transcript == "görev tamam mı"
    assert result.engine == "local_endpoint"
    assert speech.status()["state"] == "idle"


def test_listening_state_is_set_while_listening(monkeypatch):
    speech.start_listening()
    assert speech.status()["state"] == "listening"
    speech.stop()


def test_interrupt_marks_the_speech_as_cut(monkeypatch):
    speech.set_state("speaking")
    speech.interrupt()
    assert speech.status()["state"] == "idle"
    assert speech.status().get("interrupted") is True


def test_locked_vault_blocks_listening(monkeypatch):
    monkeypatch.setenv("ENABLE_LOCAL_STT", "true")
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9911/stt")
    result = asyncio.run(speech.listen(b"RIFFfake", vault_locked=True))
    assert result.available is False
    assert result.reason == "policy:vault_locked"
