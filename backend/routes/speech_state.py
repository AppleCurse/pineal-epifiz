"""Small route helper for identity-bound speech playback state transitions."""

from __future__ import annotations

import asyncio
import logging
import math

logger = logging.getLogger(__name__)
FINISH_GRACE_SECONDS = 2.0
MAX_SPEECH_FALLBACK_SECONDS = 10 * 60 + FINISH_GRACE_SECONDS


def speech_finish_delay(seconds: float) -> float:
    """Bound a watchdog delay while allowing full-length generated speech."""
    try:
        duration = float(seconds)
    except (TypeError, ValueError, OverflowError):
        duration = 0.0
    if not math.isfinite(duration):
        duration = 0.0
    return min(MAX_SPEECH_FALLBACK_SECONDS, max(0.0, duration) + FINISH_GRACE_SECONDS)


async def speech_cache_sweeper(interval_seconds: float = 60.0) -> None:
    """Periodically expire private TTS/STT files, including while idle."""
    from agent_core.capabilities.adapters_voice import prune_speech_cache

    while True:
        try:
            await asyncio.to_thread(prune_speech_cache)
        except Exception as exc:
            logger.warning("Speech cache cleanup failed: %s", type(exc).__name__)
        await asyncio.sleep(max(1.0, interval_seconds))


async def speech_finished(
    client_id: str,
    seconds: float,
    playback_id: str,
    broadcast_speech=None,
) -> None:
    """Publish idle only if this timer still belongs to the active playback."""
    try:
        await asyncio.sleep(speech_finish_delay(seconds))
    except asyncio.CancelledError:
        return

    from agent_core.services import speech

    if not speech.finish_playback(playback_id):
        return
    if broadcast_speech is None:
        from backend.api import broadcast_speech as broadcast_speech_callback

        broadcast_speech = broadcast_speech_callback
    broadcast_speech(client_id, {"state": "idle", "playback_id": playback_id})
