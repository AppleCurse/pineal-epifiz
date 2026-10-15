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
import ipaddress
import json
import math
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)

#: Metin ve ses sınırları (bellek/disk/kaynak tüketimi).
MAX_TEXT_CHARS = 2000
MAX_TTS_AUDIO_BYTES = 32 * 1024 * 1024
MAX_TTS_DURATION_MS = 10 * 60 * 1000
MIN_TTS_RATE = 0.5
MAX_TTS_RATE = 2.0

def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on", "açık"}


def speech_dir() -> str:
    return os.getenv("PINEAL_SPEECH_DIR") or os.path.join("memory", "speech")


def _private_directory(path: Path) -> None:
    """Create owner-only voice storage without chmod'ing an existing user path."""
    if path.is_symlink():
        raise OSError("voice_storage_symlink_not_allowed")
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise OSError("voice_storage_symlink_not_allowed")
    if os.name != "nt" and existed and path.stat().st_mode & 0o077:
        raise OSError("voice_storage_permissions_not_private")


def _write_private_file(path: Path, payload: bytes) -> None:
    """Create a new owner-only file without following a pre-existing symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def _local_endpoint_from_env(name: str) -> tuple[str, str]:
    """Accept only syntactically valid HTTP(S) endpoints on a loopback host."""
    url = os.getenv(name, "").strip()
    if not url:
        return "", "no_local_endpoint"
    if any(ord(char) < 32 for char in url):
        return "", "invalid_endpoint"
    try:
        parsed = urlsplit(url)
        _ = parsed.port  # force malformed/out-of-range port validation
    except (TypeError, ValueError):
        return "", "invalid_endpoint"
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return "", "bad_endpoint_scheme"
    if not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment:
        return "", "invalid_endpoint"
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost":
        return url, ""
    try:
        address = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        return "", "non_local_endpoint"
    if not address.is_loopback:
        return "", "non_local_endpoint"
    return url, ""


def _process_group_options() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


async def _stop_child_process(proc: Any) -> None:
    """Kill and reap a locally spawned process (and its POSIX process group)."""
    if proc is None or proc.returncode is not None:
        return
    try:
        pid = getattr(proc, "pid", None)
        if os.name != "nt" and pid is not None:
            os.killpg(pid, signal.SIGKILL)
        else:
            proc.kill()
    except ProcessLookupError:
        pass
    except OSError:
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=1.0)
    except (asyncio.TimeoutError, ProcessLookupError):
        pass


def _stt_command_parts() -> list[str]:
    raw = os.getenv("PINEAL_STT_CMD", "whisper").strip() or "whisper"
    try:
        return shlex.split(raw)
    except ValueError:
        return []


def is_tts_audio_name(name: str) -> bool:
    """Only content-addressed completed TTS WAV files are public to playback."""
    return bool(re.fullmatch(r"(?:[0-9a-f]{16}|[0-9a-f]{64})\.wav", str(name or "")))


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default


def speech_retention_seconds() -> int:
    """TTS retention: one hour by default, configurable from one minute to a week."""
    return _bounded_env_int("PINEAL_TTS_RETENTION_SECONDS", 3600, 60, 7 * 24 * 3600)


def speech_cache_max_bytes() -> int:
    """Bound on retained TTS audio; one maximum-sized file must always fit."""
    return _bounded_env_int(
        "PINEAL_TTS_CACHE_MAX_BYTES",
        64 * 1024 * 1024,
        MAX_TTS_AUDIO_BYTES,
        1024 * 1024 * 1024,
    )


def _remove_expired_files(directory: Path, *, older_than: float, stt_only: bool = False) -> None:
    try:
        entries = tuple(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.is_file() or entry.is_symlink():
            continue
        if stt_only and not re.fullmatch(r"in_[0-9a-f]{32}\.[a-z0-9]{1,8}", entry.name):
            continue
        try:
            if entry.stat().st_mtime < older_than:
                entry.unlink(missing_ok=True)
        except OSError:
            continue


def prune_speech_cache(now: float | None = None) -> None:
    """Expire old generated audio and crash-left voice temporaries, then bound disk use."""
    root = Path(speech_dir())
    current = time.time() if now is None else float(now)
    retention = speech_retention_seconds()
    expiration = current - retention
    try:
        entries = tuple(root.iterdir())
    except OSError:
        return

    cache: list[tuple[float, int, Path]] = []
    for entry in entries:
        if entry.name == ".stt" and entry.is_dir() and not entry.is_symlink():
            _remove_expired_files(entry, older_than=current - 300, stt_only=True)
            try:
                if not any(entry.iterdir()):
                    entry.rmdir()
            except OSError:
                pass
            continue
        try:
            if entry.is_symlink() or not entry.is_file():
                continue
            stat = entry.stat()
        except OSError:
            continue
        if is_tts_audio_name(entry.name):
            if stat.st_mtime < expiration:
                try:
                    entry.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                cache.append((stat.st_mtime, stat.st_size, entry))
        elif re.fullmatch(r"\.(?:piper|tts)_[0-9a-f]{32}\.wav", entry.name):
            if stat.st_mtime < current - 300:
                try:
                    entry.unlink(missing_ok=True)
                except OSError:
                    pass

    total = sum(size for _mtime, size, _path in cache)
    for _mtime, size, path in sorted(cache, key=lambda item: item[0]):
        if total <= speech_cache_max_bytes():
            break
        try:
            path.unlink(missing_ok=True)
            total -= size
        except OSError:
            continue


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:MAX_TEXT_CHARS]


def _wav_duration_ms(payload: bytes) -> int | None:
    """RIFF/WAV ``data`` bayt hızı üzerinden süreyi çıkarır; tahmin yapmaz."""
    if len(payload) < 44 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        return None
    try:
        riff_end = min(len(payload), struct.unpack_from("<I", payload, 4)[0] + 8)
        position = 12
        byte_rate = 0
        while position + 8 <= riff_end:
            chunk = payload[position : position + 4]
            size = struct.unpack_from("<I", payload, position + 4)[0]
            body_start = position + 8
            body_end = body_start + size
            if body_end > riff_end:
                return None
            if chunk == b"fmt " and size >= 16:
                byte_rate = struct.unpack_from("<I", payload, body_start + 8)[0]
            elif chunk == b"data":
                if not byte_rate or size <= 0:
                    return None
                return int(size * 1000 / byte_rate)
            position = body_end + (size % 2)
    except (struct.error, IndexError, ValueError, ZeroDivisionError):
        return None
    return None


def _clean_rate(value: Any) -> float:
    """Clamp the public 0.5x–2x speed contract; invalid numbers use 1x."""
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError):
        return 1.0
    if not math.isfinite(rate):
        return 1.0
    return min(MAX_TTS_RATE, max(MIN_TTS_RATE, rate))


def _local_endpoint() -> tuple[str, str]:
    """(url, '') ya da ('', sebep): yalnız YEREL uç kabul edilir."""
    return _local_endpoint_from_env("PINEAL_TTS_URL")


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
        rate = _clean_rate(ctx.params.get("rate", 1.0))

        engine, reason = self.backend()
        if not engine:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason
            )

        if engine == "piper":
            audio, engine_reason = await self._run_piper(text, voice, rate)
        else:
            audio, engine_reason = await self._run_local_endpoint(text, voice, rate)

        if not audio:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=engine_reason or "synthesis_failed",
                notes={"engine": engine},
            )
        if len(audio) > MAX_TTS_AUDIO_BYTES:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="audio_too_large",
                notes={"engine": engine, "bytes": len(audio)},
            )

        duration_ms = _wav_duration_ms(audio)
        if duration_ms is None or duration_ms <= 0:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="unsupported_or_invalid_audio_format",
                notes={"engine": engine},
            )
        if duration_ms > MAX_TTS_DURATION_MS:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="audio_duration_too_long",
                notes={"engine": engine, "duration_ms": duration_ms},
            )

        digest = hashlib.sha256(audio).hexdigest()
        target_dir = Path(speech_dir())
        temporary_path = target_dir / f".tts_{uuid.uuid4().hex}.wav"
        path = target_dir / f"{digest}.wav"
        try:
            prune_speech_cache()
            _private_directory(target_dir)
            # Stage privately and atomically publish only a complete file. Full
            # SHA-256 names avoid the 64-bit collision risk of the old prefix.
            _write_private_file(temporary_path, audio)
            os.replace(temporary_path, path)
            if os.name != "nt":
                path.chmod(0o600)
            prune_speech_cache()
        except OSError as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="write_failed",
                error=type(exc).__name__,
            )

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
                "rate": rate,
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
                "rate": rate,
                "bytes": len(audio),
                "duration_ms": duration_ms,
                "sha256": digest,
                "chars": len(text),
            },
            notes={"engine": engine, "duration_ms": duration_ms},
        )

    # ---------------------------------------------------------------- motorlar
    async def _run_piper(self, text: str, voice: str, rate: float = 1.0) -> tuple[bytes, str]:
        model = os.getenv("PINEAL_PIPER_MODEL", "").strip()
        out_path = Path(speech_dir()) / f".piper_{uuid.uuid4().hex}.wav"
        proc = None
        try:
            _private_directory(out_path.parent)
            command = [
                "piper", "--model", model, "--output_file", str(out_path),
                "--length_scale", f"{1.0 / _clean_rate(rate):.6f}",
            ]
            if voice:
                command += ["--speaker", voice]
            loop = asyncio.get_running_loop()
            started = loop.time()
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_process_group_options(),
                ),
                timeout=self.timeout_seconds,
            )
            remaining = max(0.001, self.timeout_seconds - (loop.time() - started))
            await asyncio.wait_for(
                proc.communicate(text.encode("utf-8")), timeout=remaining
            )
            if proc.returncode != 0:
                return b"", f"synthesis_failed:{proc.returncode}"
            if not out_path.is_file() or out_path.is_symlink():
                return b"", "empty_audio"
            size = out_path.stat().st_size
            if size == 0:
                return b"", "empty_audio"
            if size > MAX_TTS_AUDIO_BYTES:
                return b"", "audio_too_large"
            with out_path.open("rb") as handle:
                audio = handle.read(MAX_TTS_AUDIO_BYTES + 1)
            if len(audio) > MAX_TTS_AUDIO_BYTES:
                return b"", "audio_too_large"
            return audio, ""
        except asyncio.CancelledError:
            try:
                await asyncio.shield(_stop_child_process(proc))
            except BaseException:
                pass
            raise
        except asyncio.TimeoutError:
            await _stop_child_process(proc)
            return b"", "timeout"
        except OSError as exc:
            await _stop_child_process(proc)
            return b"", f"engine_error:{type(exc).__name__}"
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass

    async def _run_local_endpoint(self, text: str, voice: str, rate: float = 1.0) -> tuple[bytes, str]:
        url, reason = _local_endpoint()
        if not url:
            return b"", reason
        try:
            from agent_core.capabilities.egress import open_client
        except ImportError:
            return b"", "dependency_missing:httpx"

        payload: dict[str, Any] = {"text": text, "rate": _clean_rate(rate)}
        if voice:
            payload["voice"] = voice
        try:
            async with open_client(
                purpose="voice",
                target=str(url),
                timeout=self.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code >= 400:
                        return b"", f"endpoint_status:{response.status_code}"
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_TTS_AUDIO_BYTES:
                            return b"", "audio_too_large"
                        chunks.append(chunk)
        except Exception as exc:  # ağ hatası gizlenmez, sınıflandırılır
            return b"", f"endpoint_error:{type(exc).__name__}"

        audio = b"".join(chunks)
        return (audio, "") if audio else (b"", "empty_audio")


# ---------------------------------------------------------------------------
# FAZ C · C3 — YEREL STT (ses -> metin): "göz dinler"
# ---------------------------------------------------------------------------

#: Dinleme için kabul edilen ses dosyası ve motor yanıtı tavanları.
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_STT_RESPONSE_BYTES = 64 * 1024


def _local_stt_endpoint() -> tuple[str, str]:
    """(url, '') ya da ('', sebep): STT ucu da YALNIZ yerel olabilir."""
    return _local_endpoint_from_env("PINEAL_STT_URL")


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
        command = _stt_command_parts()
        if command and shutil.which(command[0]):
            return "cli", ""
        if os.getenv("PINEAL_STT_CMD", "").strip() and not command:
            return "", "invalid_command"
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

        suffix = str(ctx.params.get("suffix") or ".wav").lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
            suffix = ".wav"
        language = str(ctx.params.get("language") or os.getenv("PINEAL_STT_LANG", "") or "").strip()
        workdir = Path(speech_dir()) / ".stt"
        audio_digest = hashlib.sha256(bytes(audio)).hexdigest()
        audio_path = workdir / f"in_{uuid.uuid4().hex}{suffix}"
        try:
            _private_directory(workdir)
            _write_private_file(audio_path, bytes(audio))
        except OSError as exc:
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="write_failed",
                error=type(exc).__name__,
            )

        try:
            if engine == "cli":
                text, engine_reason = await self._run_cli(audio_path, language, workdir)
            else:
                text, engine_reason = await self._run_local_endpoint(audio_path)
        finally:
            # Microphone audio and CLI sidecar transcripts are temporary input,
            # not a recording archive. Keep only a content fingerprint in evidence.
            for temporary_path in (audio_path, workdir / f"{audio_path.stem}.txt"):
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

        text = text.strip()[:MAX_TEXT_CHARS]
        if not text:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=engine_reason or "empty_transcript",
                notes={"engine": engine},
            )

        item = make_evidence(
            content=text,
            source_engine=f"stt_{engine}",
            epistemic_type="observation",
            provenance_refs=[f"urn:sha256:{audio_digest}"],
            observed_at=datetime.now(timezone.utc),
            scope={
                "kind": "transcript",
                "engine": engine,
                "bytes": len(audio),
                "audio_sha256": audio_digest,
                "audio_retained": False,
                "chars": len(text),
                "language": language,
            },
            source_metrics={"chars": len(text), "bytes": len(audio), "audio_sha256": audio_digest},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload={"transcript": text, "engine": engine, "chars": len(text)},
            notes={"engine": engine},
        )

    async def _run_cli(self, audio_path: Path, language: str, workdir: Path) -> tuple[str, str]:
        command = _stt_command_parts()
        if not command:
            return "", "invalid_command"
        model = os.getenv("PINEAL_STT_MODEL", "base").strip() or "base"
        args = [
            *command,
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
        proc = None
        try:
            loop = asyncio.get_running_loop()
            started = loop.time()
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_process_group_options(),
                ),
                timeout=self.timeout_seconds,
            )
            remaining = max(0.001, self.timeout_seconds - (loop.time() - started))
            await asyncio.wait_for(proc.wait(), timeout=remaining)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(_stop_child_process(proc))
            except BaseException:
                pass
            raise
        except asyncio.TimeoutError:
            await _stop_child_process(proc)
            return "", "timeout"
        except OSError as exc:
            await _stop_child_process(proc)
            return "", f"engine_error:{type(exc).__name__}"

        if proc.returncode != 0:
            return "", f"transcribe_failed:{proc.returncode}"

        transcript_path = workdir / f"{audio_path.stem}.txt"
        if not transcript_path.is_file() or transcript_path.is_symlink():
            return "", "no_transcript_file"
        try:
            if transcript_path.stat().st_size > MAX_STT_RESPONSE_BYTES:
                return "", "transcript_too_large"
            with transcript_path.open("rb") as handle:
                raw = handle.read(MAX_STT_RESPONSE_BYTES + 1)
        except OSError as exc:
            return "", f"transcript_read_failed:{type(exc).__name__}"
        if len(raw) > MAX_STT_RESPONSE_BYTES:
            return "", "transcript_too_large"
        text = raw.decode("utf-8", errors="replace").strip()
        return text[:MAX_TEXT_CHARS], ""

    async def _run_local_endpoint(self, audio_path: Path) -> tuple[str, str]:
        url, reason = _local_stt_endpoint()
        if not url:
            return "", reason
        try:
            from agent_core.capabilities.egress import open_client
        except ImportError:
            return "", "dependency_missing:httpx"
        try:
            async with open_client(
                purpose="voice",
                target=str(url),
                timeout=self.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST", url, files={"file": (audio_path.name, audio_path.read_bytes())}
                ) as response:
                    if response.status_code >= 400:
                        return "", f"endpoint_status:{response.status_code}"
                    content_type = str(response.headers.get("content-type", "")).split(";", 1)[0].strip().lower()
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_STT_RESPONSE_BYTES:
                            return "", "transcript_response_too_large"
                        chunks.append(chunk)
        except Exception as exc:
            return "", f"endpoint_error:{type(exc).__name__}"
        raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not raw:
            return "", "empty_transcript"
        if content_type == "text/plain":
            return raw[:2000], ""
        if content_type == "application/json" or content_type.endswith("+json"):
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                return "", "invalid_json_transcript"
            if isinstance(parsed, dict):
                text = str(parsed.get("text") or parsed.get("transcript") or "").strip()
                return (text[:2000], "") if text else ("", "empty_transcript")
            return "", "invalid_json_transcript"
        return "", "unsupported_transcript_content_type"
