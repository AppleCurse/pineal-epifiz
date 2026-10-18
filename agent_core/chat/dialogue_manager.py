"""Diyalog yöneticisi — görev başına oturum, mesaj geçmişi ve sıralı yanıt üretimi.

Oturumlar ``task_id`` ile açılır (``start_session``); geçmiş sınırlı tutulur ve
süresi dolan/tavanı aşan oturumlar geri kazanılır (``_evict_sessions`` —
TTL ve oturum tavanı env'den okunur, ``_bounded_float`` ile doğrulanır).

``generate_response`` hedef mesajına karşılık yanıt üretir; model çağrısı
gateway üzerindendir, oturum durumu asla prompt'a ham dökülmez.

Tüketici: ``backend/api.py`` (``/api/dialogue/sessions``,
``/api/experimental/chat/respond``).
"""

import asyncio
import json
import math
import os
import time
from typing import List, Dict
from pydantic import BaseModel, Field
from agent_core.services.llm_gateway import LLMGateway

_DEFAULT_SESSION_TTL_SECONDS = 1800.0
_DEFAULT_MAX_SESSIONS = 512
_DEFAULT_MAX_HISTORY_MESSAGES = 40
_DEFAULT_MAX_MESSAGE_CHARS = 4000
_DEFAULT_MAX_PROFILE_BYTES = 16_384
MAX_DIALOGUE_MESSAGE_CHARS = _DEFAULT_MAX_MESSAGE_CHARS


class DialogueSessionCapacityError(RuntimeError):
    """A session cannot be evicted safely because all available slots are active."""


class DialogueInputError(ValueError):
    """A dialogue request violates a bounded input contract."""


class DialogueContext(BaseModel):
    task_id: str
    target_profile: dict
    user_profile: dict
    history: List[Dict[str, str]] = [] # [{"role": "target", "content": "..."}]
    # [AUDIT P2-13] Son etkinlik anı (monotonik). Oturumların süresini
    # doldurmak için gerekli; eskiden hiçbir izlenmiyordu.
    last_seen: float = 0.0

class DialogueResponse(BaseModel):
    stance: str  # "Agresif", "Savunmaci", "Ilgili", "Bilinmiyor"
    internal_analysis: str
    next_move: str = Field(max_length=MAX_DIALOGUE_MESSAGE_CHARS)

# [AUDIT P2-13] Session count, per-session history count, message size, and
# serialized profile size are all bounded; in-flight sessions are not evicted.
def _bounded_float(name: str, default: float, floor: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError, OverflowError):
        return default
    return max(floor, value) if math.isfinite(value) else default


def _bounded_int(name: str, default: int, floor: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError, OverflowError):
        return default
    return max(floor, value)


def _serialized_profile_size(profile: dict) -> int:
    try:
        encoded = json.dumps(
            profile, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise DialogueInputError("Diyalog profili JSON olarak kodlanamıyor.") from exc
    return len(encoded)


class DialogueManager:
    def __init__(self, llm_gateway: LLMGateway = None):
        self.llm = llm_gateway or LLMGateway()
        # In-memory storage for active sessions
        self.sessions: Dict[str, DialogueContext] = {}
        self.session_ttl_seconds = _bounded_float(
            "PINEAL_DIALOGUE_SESSION_TTL_SECONDS", _DEFAULT_SESSION_TTL_SECONDS, 1.0
        )
        self.max_sessions = _bounded_int(
            "PINEAL_MAX_DIALOGUE_SESSIONS", _DEFAULT_MAX_SESSIONS, 1
        )
        self.max_history_messages = _bounded_int(
            "PINEAL_MAX_DIALOGUE_MESSAGES", _DEFAULT_MAX_HISTORY_MESSAGES, 1
        )
        self.max_message_chars = _bounded_int(
            "PINEAL_MAX_DIALOGUE_MESSAGE_CHARS", _DEFAULT_MAX_MESSAGE_CHARS, 1
        )
        self.max_profile_bytes = _bounded_int(
            "PINEAL_MAX_DIALOGUE_PROFILE_BYTES", _DEFAULT_MAX_PROFILE_BYTES, 1
        )
        self._active_sessions: Dict[str, int] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self.evicted = 0

    def _evict_sessions(self, now: float, *, reserve_slot: bool = False) -> int:
        """Evict expired/old idle sessions, never a session handling a request."""
        evicted_ids = []
        expired = [
            task_id for task_id, ctx in self.sessions.items()
            if task_id not in self._active_sessions
            and now - ctx.last_seen > self.session_ttl_seconds
        ]
        for task_id in expired:
            self.sessions.pop(task_id, None)
            self._session_locks.pop(task_id, None)
            evicted_ids.append(task_id)

        # A slot is reserved only when the caller will insert a new session.
        # In-flight requests are protected even if their response takes longer
        # than the TTL or another request needs a slot while the model is waiting.
        session_limit = self.max_sessions - (1 if reserve_slot else 0)
        overflow = max(0, len(self.sessions) - session_limit)
        idle = sorted(
            (task_id for task_id in self.sessions if task_id not in self._active_sessions),
            key=lambda task_id: self.sessions[task_id].last_seen,
        )
        for task_id in idle[:overflow]:
            self.sessions.pop(task_id, None)
            self._session_locks.pop(task_id, None)
            evicted_ids.append(task_id)

        self.evicted += len(evicted_ids)
        return len(evicted_ids)

    def start_session(self, task_id: str, target_profile: dict, user_profile: dict):
        if not isinstance(target_profile, dict) or not isinstance(user_profile, dict):
            raise DialogueInputError("Diyalog profilleri nesne olmalıdır.")
        if (
            _serialized_profile_size(target_profile) > self.max_profile_bytes
            or _serialized_profile_size(user_profile) > self.max_profile_bytes
        ):
            raise DialogueInputError("Diyalog profili izin verilen boyutu aşıyor.")
        if self._active_sessions.get(task_id, 0):
            raise DialogueSessionCapacityError("Aktif diyalog oturumu sıfırlanamaz.")

        now = time.monotonic()
        is_new_session = task_id not in self.sessions
        self._evict_sessions(now, reserve_slot=is_new_session)
        if is_new_session and len(self.sessions) >= self.max_sessions:
            raise DialogueSessionCapacityError(
                "Tüm diyalog oturum yuvaları etkin; güvenli boşaltım yapılamıyor."
            )
        self.sessions[task_id] = DialogueContext(
            task_id=task_id,
            target_profile=target_profile,
            user_profile=user_profile,
            history=[],
            last_seen=now,
        )
        self._session_locks.setdefault(task_id, asyncio.Lock())

    def add_message(self, task_id: str, role: str, content: str):
        if not isinstance(content, str):
            raise DialogueInputError("Diyalog mesajı metin olmalıdır.")
        if len(content) > self.max_message_chars:
            raise DialogueInputError("Diyalog mesajı izin verilen uzunluğu aşıyor.")
        ctx = self.sessions.get(task_id)
        if ctx is not None:
            ctx.history.append({"role": role, "content": content})
            overflow = len(ctx.history) - self.max_history_messages
            if overflow > 0:
                del ctx.history[:overflow]
            ctx.last_seen = time.monotonic()

    async def generate_response(self, task_id: str, target_message: str) -> DialogueResponse:
        self._evict_sessions(time.monotonic())
        ctx = self.sessions.get(task_id)
        if ctx is None:
            raise DialogueInputError("Oturum bulunamadı veya süresi doldu.")
        if not isinstance(target_message, str) or len(target_message) > self.max_message_chars:
            raise DialogueInputError("Diyalog mesajı metin ve boyut sınırına uymalıdır.")

        # Mark active before any await so TTL/cap eviction cannot remove a
        # conversation while its model request is in flight. The lock also
        # serializes turns sharing one task_id, preserving history order.
        self._active_sessions[task_id] = self._active_sessions.get(task_id, 0) + 1
        lock = self._session_locks.setdefault(task_id, asyncio.Lock())
        try:
            async with lock:
                current = self.sessions.get(task_id)
                if current is not ctx:
                    raise ValueError("Diyalog oturumu işlem sırasında değişti.")
                ctx.last_seen = time.monotonic()

                # Add target message to history.
                self.add_message(task_id, "target", target_message)

                # Build prompt.
                history_str = "\n".join(
                    f"{message['role'].upper()}: {message['content']}"
                    for message in ctx.history
                )

                prompt = f"""
SEN BİR DİJİTAL PSİKOLOJİK HARP VE SOSYAL MÜHENDİSLİK YAPAY ZEKASISIN (PINEAL-HERETIC v3.0).
Hedefle bir konuşma içerisindesin. Aşağıda hedefin profili, senin kuralların ve şu ana kadarki diyalog geçmişi var.

HEDEF PROFİLİ:
{json.dumps(ctx.target_profile, ensure_ascii=False, indent=2)}

BİZİM PROFİLİMİZ / KUTSAL KURALLAR:
{json.dumps(ctx.user_profile, ensure_ascii=False, indent=2)}

DİYALOG GEÇMİŞİ:
{history_str}

GÖREV:
Hedefin son mesajını analiz et. Hedefin duruşunu (stance: Agresif, Savunmaci, Ilgili) belirle.
Sonrasında hedefin bu reaksiyonuna karşı, Kutsal Kuralları (örn: asla açıklama yapma, zayıflık gösterme, manipülatif ve gizemli kal) ihlal etmeyen, hedefin zayıflığını kullanacak bir 'next_move' (karşı-hamle/mesaj) üret.

YANIT FORMATI (Kati suretle JSON dön):
{{
    "stance": "Agresif",
    "internal_analysis": "Hedef neden bu tepkiyi verdi ve zafiyeti nerede?",
    "next_move": "Hedefe gönderilecek yeni manipülatif mesaj (direkt metin, tırnaksız, hazır)."
}}
"""
                response = await self.llm.query_json(prompt, DialogueResponse)

                # Add our response to history.
                self.add_message(task_id, "agent", response.next_move)
                return response
        finally:
            remaining = self._active_sessions.get(task_id, 1) - 1
            if remaining > 0:
                self._active_sessions[task_id] = remaining
            else:
                self._active_sessions.pop(task_id, None)
            if self.sessions.get(task_id) is ctx:
                ctx.last_seen = time.monotonic()
            self._evict_sessions(time.monotonic())
