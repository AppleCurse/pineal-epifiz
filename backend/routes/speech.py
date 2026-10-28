"""Authenticated speech API routes; speech generation remains local-first."""

from __future__ import annotations

import asyncio
import os
from typing import Callable

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

MAX_LISTEN_AUDIO_BYTES = 8 * 1024 * 1024


class SpeechListenResponse(BaseModel):
    """Microphone transcript and honest local-engine availability state."""

    available: bool = False
    reason: str | None = None
    state: str = "idle"
    transcript: str = ""
    engine: str | None = None
    chars: int = 0
    machine_note: str = ""


class SpeechSayPayload(BaseModel):
    """Text-to-speech request."""

    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="", max_length=64)
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    client_id: str = Field(default="default", min_length=1, max_length=128)


class SpeechFinishedPayload(BaseModel):
    """Browser playback completion, bound to the active playback UUID."""

    client_id: str = Field(default="default", min_length=1, max_length=128)
    playback_id: str = Field(pattern=r"^[0-9a-f]{32}$")

    model_config = ConfigDict(extra="forbid")


class SpeechReportPayload(BaseModel):
    """Speech report made from the result fields actually supplied."""

    client_id: str = Field(default="default", min_length=1, max_length=128)
    report: dict | None = None
    text: str = Field(default="", max_length=2000)


def build_speech_router(
    *,
    rate_limit: Callable[[str, str], bool],
    check_vault_interlock: Callable[[str], bool],
    broadcast_speech: Callable[[str, dict], None],
    broadcast_log: Callable[[str, str, str], None],
    speech_finished: Callable[..., object],
) -> APIRouter:
    """Build the speech routes with backend-owned auth, vault, and telemetry hooks."""
    router = APIRouter()

    @router.get("/api/speech/status")
    async def api_speech_status():
        """Report the actual local speech engine and playback state."""
        from agent_core.services import speech

        return speech.status()

    @router.post("/api/speech/report")
    async def api_speech_report(req: SpeechReportPayload):
        """Speak only text assembled from fields present in the supplied report."""
        from agent_core.services import speech

        if not rate_limit(f"report:{req.client_id}", "speech"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla rapor okuma isteği"}},
                status_code=429,
            )

        result = await speech.read_report(
            req.report,
            text=req.text,
            vault_locked=not check_vault_interlock(req.client_id),
        )
        payload = result.model_dump()
        if result.available:
            broadcast_speech(req.client_id, {"state": "speaking", **payload})
            duration = max(0.0, float(result.duration_ms or 0) / 1000.0)
            asyncio.create_task(
                speech_finished(req.client_id, duration, result.playback_id, broadcast_speech)
            )
            broadcast_log(req.client_id, "INFO", f"SES: {result.machine_note}")
        else:
            broadcast_speech(req.client_id, {"state": "denied", **payload})
            broadcast_log(req.client_id, "WARNING", f"SES: RAPOR OKUNAMADI: {result.reason}")
        return payload

    @router.post("/api/speech/listen", response_model=SpeechListenResponse)
    async def api_speech_listen(
        request: Request,
        client_id: str = Query(default="default", min_length=1, max_length=128),
        language: str = Query(default="", max_length=32),
    ):
        """Transcribe a bounded microphone upload using the configured local engine."""
        from agent_core.services import speech

        if not rate_limit(f"listen:{client_id}", "speech"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla dinleme isteği"}},
                status_code=429,
            )

        try:
            form = await request.form()
        except AssertionError as exc:  # Starlette reports missing multipart parser by assertion.
            if "multipart" not in str(exc).lower():
                raise
            return JSONResponse(
                {
                    "error": {
                        "code": "MULTIPART_UNAVAILABLE",
                        "message": "Dosya yükleme için python-multipart gerekli",
                    }
                },
                status_code=500,
            )
        except HTTPException as exc:
            if exc.status_code != 400:
                raise
            return JSONResponse(
                {"error": {"code": "INVALID_MULTIPART", "message": "Ses formu bozuk"}},
                status_code=400,
            )

        from starlette.datastructures import UploadFile

        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            return JSONResponse(
                {"error": {"code": "NO_AUDIO", "message": "Ses dosyası yok"}},
                status_code=400,
            )
        audio = await upload.read()
        if not audio:
            return JSONResponse(
                {"error": {"code": "EMPTY_AUDIO", "message": "Ses dosyası boş"}},
                status_code=400,
            )
        if len(audio) > MAX_LISTEN_AUDIO_BYTES:
            return JSONResponse(
                {"error": {"code": "AUDIO_TOO_LARGE", "message": "Ses dosyası çok büyük"}},
                status_code=413,
            )

        suffix = os.path.splitext(getattr(upload, "filename", "") or "")[1][:8] or ".webm"
        if speech.status()["state"] == "speaking":
            speech.interrupt()
        speech.start_listening()
        broadcast_speech(client_id, {"state": "listening"})
        result = await speech.listen(
            audio,
            suffix=suffix,
            language=language or None,
            vault_locked=not check_vault_interlock(client_id),
        )
        payload = result.model_dump()
        if result.available:
            broadcast_speech(client_id, {"state": "idle", "transcript": result.transcript})
            broadcast_log(client_id, "INFO", f"SES: duyuldu ({result.chars} karakter)")
        else:
            broadcast_speech(client_id, {"state": "denied", "reason": result.reason})
            broadcast_log(client_id, "WARNING", f"SES DUYULAMADI: {result.reason}")
        return payload

    @router.post("/api/speech/say")
    async def api_speech_say(req: SpeechSayPayload):
        """Generate local-first speech and publish its playback state."""
        from agent_core.services import speech

        if not rate_limit(f"speech:{req.client_id}", "speech"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla seslendirme isteği"}},
                status_code=429,
            )

        result = await speech.speak(
            req.text,
            voice=req.voice or None,
            rate=req.rate,
            vault_locked=not check_vault_interlock(req.client_id),
        )
        payload = result.model_dump()
        if result.available:
            broadcast_speech(req.client_id, {"state": "speaking", **payload})
            duration = max(0.0, float(result.duration_ms or 0) / 1000.0)
            asyncio.create_task(
                speech_finished(req.client_id, duration, result.playback_id, broadcast_speech)
            )
            broadcast_log(req.client_id, "INFO", f"SES: {result.machine_note}")
        else:
            broadcast_speech(req.client_id, {"state": "denied", **payload})
            broadcast_log(req.client_id, "WARNING", f"SES ÜRETİLEMEDİ: {result.reason}")
        return payload

    @router.post("/api/speech/finished")
    async def api_speech_finished(req: SpeechFinishedPayload):
        """Mark idle only if this is the playback whose browser audio ended."""
        from agent_core.services import speech

        if not speech.finish_playback(req.playback_id):
            return {"status": "stale", "playback_id": req.playback_id}
        broadcast_speech(req.client_id, {"state": "idle", "playback_id": req.playback_id})
        return {"status": "idle", "playback_id": req.playback_id}

    @router.post("/api/speech/stop")
    async def api_speech_stop(
        client_id: str = Query(default="default", min_length=1, max_length=128)
    ):
        """Interrupt current playback and publish the resulting state."""
        from agent_core.services import speech

        was_speaking = speech.status()["state"] == "speaking"
        speech.interrupt() if was_speaking else speech.stop()
        broadcast_speech(
            client_id,
            {"state": "interrupted" if was_speaking else "idle", "interrupted": was_speaking},
        )
        return {
            "status": "interrupted" if was_speaking else "stopped",
            "state": speech.status()["state"],
        }

    @router.get("/api/speech/tts")
    async def api_speech_tts(
        text: str = Query(..., min_length=1, max_length=2000),
        voice: str = Query(default="tr-TR-EmelNeural", max_length=64),
    ):
        """Free studio-grade neural TTS via edge-tts (defaults to Emel natural voice)."""
        clean = text.strip()
        if not clean:
            raise HTTPException(status_code=400, detail="EMPTY_TEXT")
        try:
            import edge_tts

            comm = edge_tts.Communicate(clean, voice)
            chunks = []
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            audio_bytes = b"".join(chunks)
            if audio_bytes:
                return Response(
                    content=audio_bytes,
                    media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="TTS_UNAVAILABLE")

    return router
