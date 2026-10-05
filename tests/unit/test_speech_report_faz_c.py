"""FAZ C · C4 — SESLİ RAPOR: metin kurucu dürüstlüğü.

Sınanan söz: rapor SESLENDİRİLİRKEN hiçbir cümle UYDURULMAZ; payload'da
olmayan alan söylenmez, kırmızı çizgi susturulmaz, kırpma gizlenmez.
"""

from __future__ import annotations

import asyncio

from agent_core.capabilities.adapters_report import (
    MAX_SCRIPT_CHARS,
    ReportScriptCapability,
    build_report_script,
)
from agent_core.capabilities.base import CapabilityContext, CapabilityKind
from agent_core.capabilities.registry import bootstrap
from agent_core.services import speech


def test_report_script_capability_is_registered():
    assert bootstrap().has("voice.report.script")


def test_capability_is_a_renderer_without_gate():
    cap = ReportScriptCapability()
    assert cap.kind is CapabilityKind.RENDERER
    assert "vault" in cap.gates


def test_empty_report_produces_no_sentence():
    script, sections = build_report_script({})
    assert script == ""
    assert sections == []


def test_script_speaks_only_what_exists():
    script, sections = build_report_script({"status": "completed"})
    assert script == "Görev tamamlandı. Rapor sonu."
    assert sections == ["status"]


def test_target_status_evidence_and_agents_are_spoken():
    script, sections = build_report_script(
        {
            "status": "completed",
            "target_profile": {"username": "salim.gumus"},
            "evidence_chain": [{"agent": "a"}, {"agent": "b"}, {"agent": "c"}],
            "runs": {
                "a": {"status": "completed", "confidence": 0.8},
                "b": {"status": "failed"},
            },
        }
    )
    assert "Hedef salim.gumus." in script
    assert "3 kayıt var" in script
    assert "2 ajan koştu, 1 tanesi tamamlandı" in script
    assert "Ortalama güven 0.80" in script
    assert "evidence" in sections


def test_confidence_sentence_is_skipped_when_no_number_exists():
    script, _ = build_report_script(
        {"runs": {"a": {"status": "completed"}}}
    )
    assert "güven" not in script


def test_change_sentence_needs_the_change_report():
    without_change, sections = build_report_script({"status": "completed"})
    assert "Geçmiş taramaya göre" not in without_change
    assert "changes" not in sections

    with_change, sections = build_report_script(
        {
            "changes": {"available": True, "added": [1, 2], "removed": [], "changed": [3]},
        }
    )
    assert "2 yeni, 0 kayıp, 1 değişen" in with_change
    assert "changes" in sections

    # Değişim raporu VAR ama temel yoksa fark UYDURULMAZ (B7 sözü).
    no_baseline, sections = build_report_script(
        {"changes": {"available": False, "reason": "no_baseline"}}
    )
    assert "Geçmiş taramaya göre" not in no_baseline
    assert "changes" not in sections


def test_red_line_is_spoken_not_silenced():
    script, sections = build_report_script({"minor_gate": {"blocked": True}})
    assert "KIRMIZI ÇİZGİ" in script
    assert "red_line" in sections


def test_free_text_is_passed_through_and_truncated_honestly():
    cap = ReportScriptCapability()
    result = asyncio.run(
        cap.run(CapabilityContext(params={"text": "x" * (MAX_SCRIPT_CHARS + 50)}))
    )
    assert result.available is True
    assert result.payload["truncated"] is True
    assert len(result.payload["script"]) == MAX_SCRIPT_CHARS + 1
    assert result.items[0].scope["kind"] == "spoken_report"


def test_read_report_without_engine_returns_the_text_but_no_audio(monkeypatch):
    monkeypatch.delenv("ENABLE_LOCAL_TTS", raising=False)
    result = asyncio.run(
        speech.read_report({"status": "completed"}, vault_locked=False)
    )
    assert result.available is False
    assert result.script  # metin yine de döner: neyin okunacağı GİZLENMEZ
    assert "uydurma ses yok" in result.machine_note


def test_read_report_rejects_empty_payload(monkeypatch):
    result = asyncio.run(speech.read_report({}, vault_locked=False))
    assert result.available is False
    assert result.reason == "empty_report"


def test_read_report_speaks_when_engine_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_LOCAL_TTS", "true")
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(tmp_path / "speech"))

    async def _fake_speak(*args, **kwargs):
        return speech.SpeechResult(
            available=True,
            state="speaking",
            engine="cli",
            voice="tr",
            name="x.wav",
            url="/api/speech/audio/x.wav",
            bytes=2048,
            duration_ms=1000,
            sha256="abc",
            chars=10,
        )

    monkeypatch.setattr(speech, "speak", _fake_speak)
    result = asyncio.run(
        speech.read_report({"status": "completed", "target_profile": {"name": "A"}}, vault_locked=False)
    )
    assert result.available is True
    assert result.script.startswith("Hedef A.")
    assert result.state == "speaking"
    assert result.url == "/api/speech/audio/x.wav"
    assert "bölüm" in result.machine_note
