"""FAZ C · C2 — YEREL SES (TTS) yeteneği: Aspasia konuşur, ses MAKİNEDE KALIR.

Röntgen bulgusu: sistemin SESİ yoktu — göz bakıyor, konuşmuyordu. Raporun
C2 maddesi: yerel TTS (VoxCPM / MOSS-TTS) ile Aspasia konuşur.

Bu adaptör Capability Spine'in **RENDERER** sınıfındadır: ses, rapor gibi bir
çıktıdır ve aynı sözleşmeden geçer (registry → politika → availability → run).

Yerellik kuralı (tartışmasız):
    * Motor **piper** (yerel CLI) ya da **PINEAL_TTS_URL** ile gösterilen
      YEREL bir sunucudur (VoxCPM / MOSS-TTS / herhangi bir yerel uç).
    * Uç yalnız ``127.0.0.1`` / ``localhost`` / ``[::1]`` olabilir; uzak bir
      adres verilirse yetenek ``non_local_endpoint`` ile REDDEDİLİR — metin
      ve ses makineden dışarı çıkmaz.
    * Motor yoksa uydurma ses ÜRETİLMEZ: `available=False` + makine-okunur
      sebep (`dependency_missing:piper`, `no_local_endpoint`, ...).

Kanıt: seslendirme bir OLAYdır ve kanıt zincirine yazılır (hangi motor, hangi
metin parmak izi, kaç bayt, kaç ms) — sonra "bunu söyledik" iddiası izlenebilir.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)

#: Metin sınırı: TTS motoruna sınırsız metin gönderilmez (maliyet + hafıza).
MAX_TEXT_CHARS = 2000

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"})


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on", "açık"}


def speech_dir() -> str:
    return os.getenv("PINEAL_SPEECH_DIR") or os.path.join("memory", "speech")


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:MAX_TEXT_CHARS]


def _wav_duration_ms(payload: bytes) -> int | None:
    """RIFF/WAV başlığından süre okunur (kütüphane yok, tahmin yok)."""
    if len(payload) < 44 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        return None
    try:
        position = 12
        while position + 8 <= len(payload):
            chunk = payload[position : position + 4]
            size = struct.unpack("<I", payload[position + 4 : position + 8])[0]
            body = payload[position + 8 : position + 8 + size]
            if chunk == b"fmt " and len(body) >= 16:
                channels, rate = struct.unpack("<HH", body[2:6])
                bits = struct.unpack("<H", body[14:16])[0]
                data_position = position + 8 + size
                while data_position + 8 <= len(payload):
                    data_chunk = payload[data_position : data_position + 4]
                    data_size = struct.unpack("<I", payload[data_position + 4 : data_position + 8])[0]
                    if data_chunk == b"data":
                        if not rate or not channels or not bits:
                            return None
                        seconds = data_size / (rate * channels * (bits // 8))
                        return int(seconds * 1000)
                    data_position += 8 + data_size + (data_size % 2)
            position += 8 + size + (size % 2)
    except (struct.error, IndexError, ValueError):
        return None
    return None


def _local_endpoint() -> tuple[str, str]:
    """(url, '') ya da ('', sebep): yalnız YEREL uç kabul edilir."""
    url = os.getenv("PINEAL_TTS_URL", "").strip()
    if not url:
        return "", "no_local_endpoint"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return "", "non_local_endpoint"
    if parsed.scheme not in {"http", "https"}:
        return "", "bad_endpoint_scheme"
    return url, ""


class LocalTTSCapability(BaseCapability):
    """Yerel metin→ses: piper CLI ya da YEREL bir TTS ucu (VoxCPM/MOSS-TTS).

    Ağa çıkış YOKTUR (uç yalnız localhost olabilir); motor yoksa uydurma ses
    üretilmez. Çıktı ses dosyası + kanıt kaydıdır.
    """

    id = "voice.tts.local"
    kind = CapabilityKind.RENDERER
    license = "harici süreç/yerel uç (kod gömülmez)"
    # Kasa kapısı DAHİL: Tüzük Md.4 — kasa kilitliyken kayıtlı hiçbir yetenek
    # koşamaz (istisna yok). Ses yerel üretilse de kural aynıdır.
    gates = frozenset({"vault", "ENABLE_LOCAL_TTS"})
    timeout_seconds = 60.0
    description = "Yerel TTS (piper CLI veya localhost TTS ucu) — ses makineden çıkmaz."

    # ------------------------------------------------------------------ durum
    def backend(self) -> tuple[str, str]:
        """(motor adı, '') ya da ('', sebep)."""
        if shutil.which("piper") and os.getenv("PINEAL_PIPER_MODEL", "").strip():
            return "piper", ""
        url, reason = _local_endpoint()
        if url:
            return "local_endpoint", ""
        return "", reason

    def availability(self) -> Availability:
        engine, reason = self.backend()
        if not engine:
            return Availability.unavailable(reason)
        return Availability.ok()

    # -------------------------------------------------------------------- koşu
    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        text = _clean_text(str(ctx.params.get("text") or ctx.subject or ""))
        if not text:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_text"
            )
        voice = str(ctx.params.get("voice") or os.getenv("PINEAL_TTS_VOICE", "") or "").strip()

        engine, reason = self.backend()
        if not engine:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason
            )

        if engine == "piper":
            audio, engine_reason = await self._run_piper(text, voice)
        else:
            audio, engine_reason = await self._run_local_endpoint(text, voice)

        if not audio:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=engine_reason or "synthesis_failed",
                notes={"engine": engine},
            )

        digest = hashlib.sha256(audio).hexdigest()
        suffix = ".wav" if audio[:4] == b"RIFF" else ".audio"
        target_dir = Path(speech_dir())
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / f"{digest[:16]}{suffix}"
            if not path.exists():
                path.write_bytes(audio)
        except OSError as exc:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="write_failed",
                error=type(exc).__name__,
            )

        duration_ms = _wav_duration_ms(audio)
        item = make_evidence(
            content=f"Seslendirildi [{engine}]: {text[:120]}",
            source_engine=f"tts_{engine}",
            epistemic_type="observation",
            provenance_refs=[str(path)],
            observed_at=datetime.now(timezone.utc),
            scope={
                "kind": "speech",
                "engine": engine,
                "voice": voice,
                "sha256": digest,
                "bytes": len(audio),
                "duration_ms": duration_ms,
                "chars": len(text),
            },
            source_metrics={"bytes": len(audio), "duration_ms": duration_ms},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload={
                "path": str(path),
                "name": path.name,
                "engine": engine,
                "voice": voice,
                "bytes": len(audio),
                "duration_ms": duration_ms,
                "sha256": digest,
                "chars": len(text),
            },
            notes={"engine": engine, "duration_ms": duration_ms},
        )

    # ---------------------------------------------------------------- motorlar
    async def _run_piper(self, text: str, voice: str) -> tuple[bytes, str]:
        model = os.getenv("PINEAL_PIPER_MODEL", "").strip()
        out_path = Path(speech_dir()) / f".piper_{hashlib.sha256(text.encode()).hexdigest()[:16]}.wav"
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            command = ["piper", "--model", model, "--output_file", str(out_path)]
            if voice:
                command += ["--speaker", voice]
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self.timeout_seconds,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(text.encode("utf-8")), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            return b"", "timeout"
        except (OSError, FileNotFoundError) as exc:
            return b"", f"engine_error:{type(exc).__name__}"

        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", "replace").strip()[:160]
            return b"", f"synthesis_failed:{detail or proc.returncode}"
        if not out_path.exists() or out_path.stat().st_size == 0:
            return b"", "empty_audio"
        audio = out_path.read_bytes()
        return audio, ""

    async def _run_local_endpoint(self, text: str, voice: str) -> tuple[bytes, str]:
        url, reason = _local_endpoint()
        if not url:
            return b"", reason
        try:
            import httpx
        except ImportError:
            return b"", "dependency_missing:httpx"

        payload: dict[str, Any] = {"text": text}
        if voice:
            payload["voice"] = voice
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload)
        except Exception as exc:  # ağ hatası gizlenmez, sınıflandırılır
            return b"", f"endpoint_error:{type(exc).__name__}"

        if response.status_code >= 400:
            return b"", f"endpoint_status:{response.status_code}"
        if not response.content:
            return b"", "empty_audio"
        return response.content, ""


# ---------------------------------------------------------------------------
# FAZ C · C3 — YEREL STT (ses -> metin): "göz dinler"
# ---------------------------------------------------------------------------

#: Dinleme için kabul edilen ses dosyası tavanı (bellek/disk sınırı).
MAX_AUDIO_BYTES = 8 * 1024 * 1024


def _local_stt_endpoint() -> tuple[str, str]:
    """(url, '') ya da ('', sebep): STT ucu da YALNIZ yerel olabilir."""
    url = os.getenv("PINEAL_STT_URL", "").strip()
    if not url:
        return "", "no_local_endpoint"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return "", "non_local_endpoint"
    if parsed.scheme not in {"http", "https"}:
        return "", "bad_endpoint_scheme"
    return url, ""


class LocalSTTCapability(BaseCapability):
    """Yerel konuşma tanıma: `whisper` CLI ya da YEREL bir STT ucu.

    Ses MAKİNEDEN ÇIKMAZ (uç yalnız localhost). Motor yoksa uydurma
    transkript ÜRETİLMEZ: `available=False` + makine-okunur sebep.
    """

    id = "voice.stt.local"
    kind = CapabilityKind.EXTRACTOR
    license = "harici süreç/yerel uç (kod gömülmez)"
    gates = frozenset({"vault", "ENABLE_LOCAL_STT"})
    timeout_seconds = 120.0
    description = "Yerel konuşma tanıma (whisper CLI veya localhost STT ucu)."

    def backend(self) -> tuple[str, str]:
        url, reason = _local_stt_endpoint()
        if url:
            return "local_endpoint", ""
        if shutil.which(os.getenv("PINEAL_STT_CMD", "whisper") or "whisper"):
            return "cli", ""
        return "", reason

    def availability(self) -> Availability:
        engine, reason = self.backend()
        if not engine:
            return Availability.unavailable(reason)
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        audio = ctx.params.get("audio") or b""
        if not isinstance(audio, (bytes, bytearray)) or not audio:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_audio"
            )
        if len(audio) > MAX_AUDIO_BYTES:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="audio_too_large"
            )

        engine, reason = self.backend()
        if not engine:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason
            )

        suffix = str(ctx.params.get("suffix") or ".wav")
        language = str(ctx.params.get("language") or os.getenv("PINEAL_STT_LANG", "") or "").strip()
        workdir = Path(speech_dir()) / ".stt"
        try:
            workdir.mkdir(parents=True, exist_ok=True)
            audio_path = workdir / f"in_{hashlib.sha256(bytes(audio)).hexdigest()[:16]}{suffix}"
            if not audio_path.exists():
                audio_path.write_bytes(bytes(audio))
        except OSError as exc:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="write_failed",
                error=type(exc).__name__,
            )

        if engine == "cli":
            text, engine_reason = await self._run_cli(audio_path, language, workdir)
        else:
            text, engine_reason = await self._run_local_endpoint(audio_path)

        if not text:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=engine_reason or "empty_transcript",
                notes={"engine": engine},
            )

        item = make_evidence(
            content=text[:2000],
            source_engine=f"stt_{engine}",
            epistemic_type="observation",
            provenance_refs=[str(audio_path)],
            observed_at=datetime.now(timezone.utc),
            scope={
                "kind": "transcript",
                "engine": engine,
                "bytes": len(audio),
                "chars": len(text),
                "language": language,
            },
            source_metrics={"chars": len(text), "bytes": len(audio)},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload={"transcript": text, "engine": engine, "chars": len(text)},
            notes={"engine": engine},
        )

    async def _run_cli(self, audio_path: Path, language: str, workdir: Path) -> tuple[str, str]:
        command = os.getenv("PINEAL_STT_CMD", "whisper").strip() or "whisper"
        model = os.getenv("PINEAL_STT_MODEL", "base").strip() or "base"
        args = [
            command,
            str(audio_path),
            "--model",
            model,
            "--output_format",
            "txt",
            "--output_dir",
            str(workdir),
        ]
        if language:
            args += ["--language", language]
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self.timeout_seconds,
            )
            _stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            return "", "timeout"
        except (OSError, FileNotFoundError) as exc:
            return "", f"engine_error:{type(exc).__name__}"

        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", "replace").strip()[:160]
            return "", f"transcribe_failed:{detail or proc.returncode}"

        transcript_path = workdir / f"{audio_path.stem}.txt"
        if not transcript_path.exists():
            return "", "no_transcript_file"
        text = transcript_path.read_text(encoding="utf-8", errors="replace").strip()
        return text, ""

    async def _run_local_endpoint(self, audio_path: Path) -> tuple[str, str]:
        url, reason = _local_stt_endpoint()
        if not url:
            return "", reason
        try:
            import httpx
        except ImportError:
            return "", "dependency_missing:httpx"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url, files={"file": (audio_path.name, audio_path.read_bytes())}
                )
        except Exception as exc:
            return "", f"endpoint_error:{type(exc).__name__}"
        if response.status_code >= 400:
            return "", f"endpoint_status:{response.status_code}"
        raw = (response.text or "").strip()
        if not raw:
            return "", "empty_transcript"
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                text = str(parsed.get("text") or parsed.get("transcript") or "").strip()
                if text:
                    return text, ""
        except (ValueError, TypeError):
            pass
        return raw, ""
