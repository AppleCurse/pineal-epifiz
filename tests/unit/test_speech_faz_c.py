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
import sys
import time

from agent_core.capabilities.adapters_voice import (
    LocalSTTCapability,
    LocalTTSCapability,
    MAX_TTS_DURATION_MS,
    _local_endpoint,
    _local_stt_endpoint,
    _process_group_options,
    _stop_child_process,
    _stt_command_parts,
    _wav_duration_ms,
    is_tts_audio_name,
    prune_speech_cache,
)
from agent_core.capabilities.base import CapabilityContext, CapabilityKind
from agent_core.capabilities.registry import bootstrap
from agent_core.services import speech


def _wav(seconds: float = 1.5, rate: int = 8000) -> bytes:

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


def test_voice_endpoints_reject_credentials_bad_ports_and_non_loopback_hosts(monkeypatch):
    for value in (
        "http://user:secret@127.0.0.1:9911/tts",
        "http://127.0.0.1:99999/tts",
        "http://192.168.1.10:9911/tts",
        "http://127.0.0.1:9911/tts#secret",
    ):
        monkeypatch.setenv("PINEAL_TTS_URL", value)
        url, reason = _local_endpoint()
        assert url == ""
        assert reason in {"invalid_endpoint", "non_local_endpoint"}

    monkeypatch.setenv("PINEAL_STT_URL", "http://localhost:9911/stt")
    url, reason = _local_stt_endpoint()
    assert url == "http://localhost:9911/stt"
    assert reason == ""


def test_stt_command_override_is_parsed_as_argv_not_shell(monkeypatch):
    monkeypatch.setenv("PINEAL_STT_CMD", f'{sys.executable} -m whisper')
    assert _stt_command_parts() == [sys.executable, "-m", "whisper"]
    monkeypatch.setenv("PINEAL_STT_CMD", "whisper 'unclosed")
    assert _stt_command_parts() == []


def test_tts_audio_name_is_a_strict_allowlist():
    assert is_tts_audio_name("0123456789abcdef.wav")
    assert is_tts_audio_name("a" * 64 + ".wav")
    assert not is_tts_audio_name("../0123456789abcdef.wav")
    assert not is_tts_audio_name(".piper_0123456789abcdef0123456789abcdef.wav")
    assert not is_tts_audio_name("notes.wav")


def test_speech_cache_expires_private_files_and_enforces_byte_limit(monkeypatch, tmp_path):
    root = tmp_path / "speech"
    root.mkdir()
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(root))
    monkeypatch.setenv("PINEAL_TTS_RETENTION_SECONDS", "60")
    monkeypatch.setenv("PINEAL_TTS_CACHE_MAX_BYTES", str(32 * 1024 * 1024))
    now = time.time()

    expired = root / "aaaaaaaaaaaaaaaa.wav"
    fresh = root / "bbbbbbbbbbbbbbbb.wav"
    expired.write_bytes(b"expired")
    fresh.write_bytes(b"fresh")
    os.utime(expired, (now - 61, now - 61))

    piper_temp = root / ".piper_0123456789abcdef0123456789abcdef.wav"
    piper_temp.write_bytes(b"partial")
    os.utime(piper_temp, (now - 301, now - 301))
    stt_dir = root / ".stt"
    stt_dir.mkdir()
    stt_temp = stt_dir / "in_0123456789abcdef0123456789abcdef.webm"
    stt_temp.write_bytes(b"private audio")
    os.utime(stt_temp, (now - 301, now - 301))
    unrelated = stt_dir / "keep.txt"
    unrelated.write_text("unrelated", encoding="utf-8")

    oldest = root / "cccccccccccccccc.wav"
    newest = root / "dddddddddddddddd.wav"
    for cache_file in (oldest, newest):
        with cache_file.open("wb") as stream:
            stream.truncate(20 * 1024 * 1024)
    os.utime(oldest, (now - 10, now - 10))
    os.utime(newest, (now - 5, now - 5))

    prune_speech_cache(now)

    assert not expired.exists()
    assert fresh.exists()
    assert not piper_temp.exists()
    assert not stt_temp.exists()
    assert unrelated.exists()
    assert not oldest.exists()
    assert newest.exists()


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

    async def _fake(self, text, voice, rate=1.0):  # yerel motorun yerine geçer
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
    assert payload["rate"] == 1.0
    assert payload["duration_ms"] == 1500, "süre WAV başlığından okunmadı"
    assert os.path.exists(payload["path"])
    assert payload["name"] == payload["sha256"] + ".wav"
    if os.name != "nt":
        assert os.stat(payload["path"]).st_mode & 0o777 == 0o600
        assert os.stat(os.path.dirname(payload["path"])).st_mode & 0o777 == 0o700
    item = result.items[0]
    assert item.scope["kind"] == "speech"
    assert item.scope["sha256"] == payload["sha256"]
    assert "Mösyö" in item.content


def test_failed_synthesis_produces_no_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")

    async def _fake(self, text, voice, rate=1.0):
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

    async def _fake(self, text, voice, rate=1.0):
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
    assert _wav_duration_ms(_wav(2.0, rate=96000)) == 2000
    assert _wav_duration_ms(b"not audio at all") is None
    assert _wav_duration_ms(b"") is None


def test_tts_rejects_impossible_wav_duration_before_scheduling_playback(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")
    malformed_rate = bytearray(_wav(0.5))
    struct.pack_into("<I", malformed_rate, 28, 1)
    assert _wav_duration_ms(bytes(malformed_rate)) > MAX_TTS_DURATION_MS

    async def _fake(self, text, voice, rate=1.0):
        return bytes(malformed_rate), ""

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(LocalTTSCapability().run(CapabilityContext(params={"text": "merhaba"})))
    assert result.available is False
    assert result.unavailable_reason == "audio_duration_too_long"
    assert result.items == ()


def test_process_group_cleanup_reaps_a_cancelled_style_child():
    async def _run():
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            **_process_group_options(),
        )
        await _stop_child_process(child)
        assert child.returncode is not None

    asyncio.run(_run())


def test_tts_rejects_non_wav_payload_instead_of_serving_it_as_audio_wav(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")

    async def _fake(self, text, voice, rate=1.0):
        return b"ID3-not-a-wave", ""

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(LocalTTSCapability().run(CapabilityContext(params={"text": "merhaba"})))
    assert result.available is False
    assert result.unavailable_reason == "unsupported_or_invalid_audio_format"
    assert result.items == ()


def test_tts_rate_is_clamped_and_recorded(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_TTS_URL", "http://127.0.0.1:9911/tts")
    seen = {}

    async def _fake(self, text, voice, rate=1.0):
        seen["rate"] = rate
        return _wav(0.5), ""

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(LocalTTSCapability().run(
        CapabilityContext(params={"text": "merhaba", "rate": 9.0})
    ))
    assert result.available is True
    assert seen["rate"] == 2.0
    assert result.payload["rate"] == 2.0
    assert result.items[0].scope["rate"] == 2.0


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
    speech.set_state(speech.STATE_SPEAKING)
    speech.interrupt()
    assert speech.status()["interrupted"] is True

    async def _fake(self, text, voice, rate=1.0):
        return _wav(1.0), ""

    monkeypatch.setattr(LocalTTSCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(speech.speak("Mösyö, görev tamam.", vault_locked=False))
    assert result.available is True
    assert result.state == "speaking"
    assert speech.status()["interrupted"] is False
    assert result.rate == 1.0
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

    async def _fake(self, text, voice, rate=1.0):
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


def test_stt_transcribes_ephemeral_audio_and_keeps_fingerprint_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))
    monkeypatch.setenv("PINEAL_STT_URL", "http://127.0.0.1:9911/stt")
    seen = {}

    async def _fake(self, audio_path):
        seen["path"] = audio_path
        return "Mösyö, bu hedefin son iki haftasını göster.", ""

    monkeypatch.setattr(LocalSTTCapability, "_run_local_endpoint", _fake)
    result = asyncio.run(LocalSTTCapability().run(CapabilityContext(params={
        "audio": b"RIFFfake",
        "suffix": "../../escape.wav",
    })))
    assert result.available is True
    assert result.payload["transcript"].startswith("Mösyö")
    assert result.items[0].scope["kind"] == "transcript"
    assert result.items[0].scope["audio_retained"] is False
    assert result.items[0].scope["audio_sha256"]
    assert result.items[0].provenance_refs[0].startswith("urn:sha256:")
    assert result.items[0].content.startswith("Mösyö")
    assert seen["path"].parent == tmp_path / "speech" / ".stt"
    assert seen["path"].suffix == ".wav"
    assert list((tmp_path / "speech" / ".stt").iterdir()) == []


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
    assert list((tmp_path / "speech" / ".stt").iterdir()) == []


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
