"""Private, time-bounded playback endpoint for generated TTS WAV files."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path as FilePath

from fastapi import APIRouter, Path
from fastapi.responses import FileResponse, JSONResponse

from agent_core.capabilities.adapters_voice import (
    is_tts_audio_name,
    prune_speech_cache,
    speech_dir,
)
from agent_core.utils.security import safe_child_path

router = APIRouter()


@router.get("/api/speech/audio/{name}")
async def api_speech_audio(name: str = Path(min_length=1, max_length=128)):
    """Serve only an unexpired generated file; never expose temp/other files."""
    if not is_tts_audio_name(name):
        return JSONResponse(
            {"error": {"code": "INVALID_AUDIO_NAME", "message": "Geçersiz ses dosyası"}},
            status_code=400,
        )

    await asyncio.to_thread(prune_speech_cache)
    if (FilePath(speech_dir()) / name).is_symlink():
        return JSONResponse(
            {"error": {"code": "INVALID_AUDIO_NAME", "message": "Geçersiz ses dosyası"}},
            status_code=400,
        )
    try:
        path = safe_child_path(speech_dir(), name)
    except ValueError:
        return JSONResponse(
            {"error": {"code": "INVALID_AUDIO_NAME", "message": "Geçersiz ses dosyası"}},
            status_code=400,
        )
    if not os.path.isfile(path):
        return JSONResponse(
            {"error": {"code": "NOT_FOUND", "message": "Ses dosyası yok veya süresi dolmuş"}},
            status_code=404,
        )
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=name,
        headers={"Cache-Control": "private, no-store"},
    )
