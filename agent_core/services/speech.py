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
#: [FAZ C · C3] Göz DİNLER ve SUSAR: dinleme + araya girme halleri.
STATE_LISTENING = "listening"
STATE_INTERRUPTED = "interrupted"

STT_CAPABILITY_ID = "voice.stt.local"
STT_GATE = "ENABLE_LOCAL_STT"

#: Konuşma durumlarının tamamı (UI bu listeyi gösterir).
KNOWN_STATES = (
    STATE_IDLE,
    STATE_LISTENING,
    STATE_SPEAKING,
    STATE_INTERRUPTED,
    STATE_DENIED,
)


class ListenResult(BaseModel):
    """Dinlemenin dürüst sonucu: transkript ya da sebep (uydurma metin yok)."""

    available: bool = False
    reason: str = ""
    state: str = STATE_IDLE
    transcript: str = ""
    engine: str = ""
    chars: int = 0
    machine_note: str = ""

    model_config = ConfigDict(extra="forbid")


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
    """Motorların BUGÜNKÜ dürüst durumu (yoksa neden yok): TTS + STT."""
    from agent_core.capabilities.adapters_voice import (
        LocalSTTCapability,
        LocalTTSCapability,
    )

    tts = LocalTTSCapability()
    stt = LocalSTTCapability()
    tts_engine, tts_reason = tts.backend()
    stt_engine, stt_reason = stt.backend()
    return {
        "capability_id": CAPABILITY_ID,
        "gate": GATE,
        "gate_enabled": _flag(GATE),
        "engine": tts_engine or "",
        "available": bool(tts.availability().available),
        "reason": tts.availability().reason or tts_reason or "",
        "tts": {
            "capability_id": CAPABILITY_ID,
            "gate": GATE,
            "gate_enabled": _flag(GATE),
            "engine": tts_engine or "",
            "available": bool(tts.availability().available),
            "reason": tts.availability().reason or tts_reason or "",
        },
        "stt": {
            "capability_id": STT_CAPABILITY_ID,
            "gate": STT_GATE,
            "gate_enabled": _flag(STT_GATE),
            "engine": stt_engine or "",
            "available": bool(stt.availability().available),
            "reason": stt.availability().reason or stt_reason or "",
        },
        "machine_note": (
            f"SES: konuşma={tts_engine or 'yok'} · dinleme={stt_engine or 'yok'} · "
            f"kapılar {GATE}={'açık' if _flag(GATE) else 'kapalı'}, "
            f"{STT_GATE}={'açık' if _flag(STT_GATE) else 'kapalı'}"
        ),
    }


def status() -> Dict[str, Any]:
    """Ses durumunun tamamı: motor + konuşma durumu + son seslendirme."""
    payload = engine_status()
    payload["state"] = _STATE.get("state", STATE_IDLE)
    payload["last"] = _STATE.get("last")
    payload["last_heard"] = _STATE.get("last_heard")
    #: Araya girme izi: son konuşma KESİLDİ mi, hangi hâldeyken kesildi?
    payload["interrupted"] = bool(_STATE.get("interrupted", False))
    payload["interrupted_from"] = _STATE.get("interrupted_from")
    payload["known_states"] = list(KNOWN_STATES)
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


def start_listening() -> None:
    """Dinleme başlar (göz büyür). Tek durum geçidi."""
    set_state(STATE_LISTENING)


def interrupt() -> None:
    """Araya girme: konuşma KESİLİR ve izi bırakılır (hangi hâlde kesildi)."""
    cut_from = str(_STATE.get("state") or STATE_IDLE)
    set_state(STATE_INTERRUPTED, interrupted=True, interrupted_from=cut_from)
    set_state(STATE_IDLE, interrupted=True, interrupted_from=cut_from)


def clear_interrupt() -> None:
    """Araya girme izini temizler (yeni bir konuşma başlarken)."""
    _STATE.pop("interrupted", None)
    _STATE.pop("interrupted_from", None)


def stop() -> None:
    """Konuşmayı kes (C3'teki 'araya girme' için tek durum geçidi)."""
    set_state(STATE_IDLE)


async def listen(
    audio: bytes,
    *,
    suffix: str = ".wav",
    language: str = "",
    vault_locked: bool = True,
    emit: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> ListenResult:
    """Sesi METNE çevirir (tek geçit: `voice.stt.local` yeteneği).

    Kasa kuralı konuşmayla aynıdır: durum bilinmiyorsa kilitli sayılır.
    Motor yoksa uydurma transkript DÖNMEZ.
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner

    start_listening()
    registry = bootstrap()
    runner = CapabilityRunner(registry=registry, emit=emit)
    state = PolicyState(
        enabled_flags={STT_GATE: _flag(STT_GATE)},
        vault_locked=bool(vault_locked),
        rate_ok=True,
    )
    result = await runner.run(
        STT_CAPABILITY_ID,
        CapabilityContext(params={"audio": audio, "suffix": suffix, "language": language}),
        state=state,
    )

    payload: Dict[str, Any] = dict(result.payload or {})
    if not result.available or not payload:
        reason = str(result.unavailable_reason or result.denied_by or result.error or "unavailable")
        set_state(STATE_DENIED, reason=reason)
        return ListenResult(
            available=False,
            reason=reason,
            state=STATE_DENIED,
            machine_note=f"SES: duyulamadı — {reason} (uydurma transkript yok)",
        )

    transcript = str(payload.get("transcript") or "").strip()
    heard = ListenResult(
        available=True,
        state=STATE_IDLE,
        transcript=transcript,
        engine=str(payload.get("engine") or ""),
        chars=len(transcript),
        machine_note=f"SES: {payload.get('engine')} · {len(transcript)} karakter duyuldu",
    )
    set_state(STATE_IDLE, last_heard=heard.model_dump())
    return heard
