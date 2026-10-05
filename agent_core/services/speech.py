"""FAZ C · C2 — SES SERVİSİ: Aspasia konuşur (tek geçit = Capability Spine).

Bu katman TTS motorunu DOĞRUDAN çağırmaz: iş, `voice.tts.local` yeteneğinden
geçer (registry → politika kapıları → availability → run → kanıt). Böylece ses
de her yetenek gibi tek sözleşmeye, tek telemetriye ve tek güvenlik
çekirdeğine bağlıdır — paralel bir çağrı yolu yoktur.

Dışarı sızma kuralı: motor yereldir (piper CLI veya localhost ucu); yetenek
uzak uç görürse reddeder. Bu servis de o kararı AYNIEN aktarır.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

CAPABILITY_ID = "voice.tts.local"
GATE = "ENABLE_LOCAL_TTS"

STATE_IDLE = "idle"
STATE_SPEAKING = "speaking"
STATE_DENIED = "denied"


class SpeechResult(BaseModel):
    """Tek konuşma denemesinin dürüst sonucu."""

    available: bool = False
    reason: str = ""
    state: str = STATE_IDLE
    engine: str = ""
    voice: str = ""
    name: str = ""
    url: str = ""
    bytes: int = 0
    duration_ms: Optional[int] = None
    sha256: str = ""
    chars: int = 0
    machine_note: str = ""

    model_config = ConfigDict(extra="forbid")


#: Konuşma durumu (C3'te dinleme/araya girme ile birleşecek tek yer).
_STATE: Dict[str, Any] = {"state": STATE_IDLE, "last": None, "updated_at": 0.0}


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on", "açık"}


def set_state(state: str, **extra: Any) -> None:
    """Konuşma durumunu günceller (UI'a WebSocket'ten akar)."""
    _STATE["state"] = state
    _STATE["updated_at"] = time.time()
    if "last" in extra:
        _STATE["last"] = extra["last"]
    _STATE.update({k: v for k, v in extra.items() if k != "last"})


def engine_status() -> Dict[str, Any]:
    """Motorun BUGÜNKÜ dürüst durumu (yoksa neden yok)."""
    from agent_core.capabilities.adapters_voice import LocalTTSCapability

    capability = LocalTTSCapability()
    availability = capability.availability()
    engine, reason = capability.backend()
    return {
        "capability_id": CAPABILITY_ID,
        "gate": GATE,
        "gate_enabled": _flag(GATE),
        "engine": engine or "",
        "available": bool(availability.available),
        "reason": availability.reason or reason or "",
        "machine_note": (
            f"SES: motor={engine or 'yok'} · kapı {GATE}={'açık' if _flag(GATE) else 'kapalı'}"
            + (f" · {availability.reason}" if not availability.available else "")
        ),
    }


def status() -> Dict[str, Any]:
    """Ses durumunun tamamı: motor + konuşma durumu + son seslendirme."""
    payload = engine_status()
    payload["state"] = _STATE.get("state", STATE_IDLE)
    payload["last"] = _STATE.get("last")
    payload["updated_at"] = _STATE.get("updated_at", 0.0)
    return payload


async def speak(
    text: str,
    *,
    voice: Optional[str] = None,
    vault_locked: bool = True,
    emit: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> SpeechResult:
    """Metni seslendirir (tek geçit: yetenek omurgası). Uydurma ses yok.

    `vault_locked` BİLİNÇLİ olarak varsayılan ``True``: durum bilinmiyorsa
    kasa kilitli sayılır (Tüzük Md.4, fail-closed). Açık kasa bilgisi
    çağırandan gelir (oda interlock'u).
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner

    registry = bootstrap()
    runner = CapabilityRunner(registry=registry, emit=emit)
    state = PolicyState(
        enabled_flags={GATE: _flag(GATE)},
        vault_locked=bool(vault_locked),
        rate_ok=True,
    )
    result = await runner.run(
        CAPABILITY_ID,
        CapabilityContext(
            subject="",
            params={"text": text, "voice": voice or ""},
        ),
        state=state,
    )

    payload: Dict[str, Any] = dict(result.payload or {})
    if not result.available or not payload:
        reason = str(
            result.unavailable_reason
            or result.denied_by
            or result.error
            or "unavailable"
        )
        set_state(STATE_DENIED, reason=reason)
        return SpeechResult(
            available=False,
            reason=reason,
            state=STATE_DENIED,
            machine_note=f"SES: seslendirilemedi — {reason} (uydurma ses yok)",
        )

    name = str(payload.get("name") or "")
    spoken = SpeechResult(
        available=True,
        state=STATE_SPEAKING,
        engine=str(payload.get("engine") or ""),
        voice=str(payload.get("voice") or ""),
        name=name,
        url=f"/api/speech/audio/{name}" if name else "",
        bytes=int(payload.get("bytes") or 0),
        duration_ms=payload.get("duration_ms"),
        sha256=str(payload.get("sha256") or ""),
        chars=int(payload.get("chars") or 0),
        machine_note=(
            f"SES: {payload.get('engine')} · {payload.get('bytes')} bayt · "
            f"{payload.get('duration_ms') or '?'} ms · {payload.get('chars')} karakter seslendirildi"
        ),
    )
    set_state(STATE_SPEAKING, last=spoken.model_dump())
    return spoken


def stop() -> None:
    """Konuşmayı kes (C3'teki 'araya girme' için tek durum geçidi)."""
    set_state(STATE_IDLE)
