import json
import os
import time
from typing import List, Dict
from pydantic import BaseModel
from agent_core.services.llm_gateway import LLMGateway
from agent_core.version import VERSION

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
    next_move: str

# [AUDIT P2-13] Ölçülen: 50.000 start_session -> 50.000 kalıcı DialogueContext /
# 58.0 MB, girdi başına 1.217 bayt ve HİÇBİRİ asla silinmiyordu. "Oturum
# bulunamadı veya süresi doldu" hatası bir süre ima ediyordu ama süreyi
# uygulayan tek satır kod yoktu. Sınırlar rooms ile aynı desende.
_DEFAULT_SESSION_TTL_SECONDS = 1800.0
_DEFAULT_MAX_SESSIONS = 512


def _bounded_float(name: str, default: float, floor: float) -> float:
    try:
        return max(floor, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class DialogueManager:
    def __init__(self, llm_gateway: LLMGateway = None):
        self.llm = llm_gateway or LLMGateway()
        # In-memory storage for active sessions
        self.sessions: Dict[str, DialogueContext] = {}
        self.session_ttl_seconds = _bounded_float(
            "PINEAL_DIALOGUE_SESSION_TTL_SECONDS", _DEFAULT_SESSION_TTL_SECONDS, 1.0
        )
        self.max_sessions = max(1, int(_bounded_float(
            "PINEAL_MAX_DIALOGUE_SESSIONS", _DEFAULT_MAX_SESSIONS, 1.0
        )))
        self.evicted = 0

    def _evict_sessions(self, now: float) -> int:
        """Süresi dolmuş ve tavan aşımındaki oturumları geri kazanır."""
        expired = [
            task_id for task_id, ctx in self.sessions.items()
            if now - ctx.last_seen > self.session_ttl_seconds
        ]
        for task_id in expired:
            del self.sessions[task_id]
        # -1: çağıran hemen ardından yeni bir oturum ekleyecek; tavanı
        # aşmamak için yer açılır (aksi halde kalıcı durum cap+1 oluyordu).
        overflow = len(self.sessions) - (self.max_sessions - 1)
        if overflow > 0:
            for task_id in sorted(self.sessions, key=lambda t: self.sessions[t].last_seen)[:overflow]:
                del self.sessions[task_id]
        self.evicted += len(expired) + max(0, overflow)
        return len(expired) + max(0, overflow)

    def start_session(self, task_id: str, target_profile: dict, user_profile: dict):
        now = time.monotonic()
        self._evict_sessions(now)
        self.sessions[task_id] = DialogueContext(
            task_id=task_id,
            target_profile=target_profile,
            user_profile=user_profile,
            history=[],
            last_seen=now,
        )

    def add_message(self, task_id: str, role: str, content: str):
        ctx = self.sessions.get(task_id)
        if ctx is not None:
            ctx.history.append({"role": role, "content": content})
            ctx.last_seen = time.monotonic()

    async def generate_response(self, task_id: str, target_message: str) -> DialogueResponse:
        self._evict_sessions(time.monotonic())
        if task_id not in self.sessions:
            raise ValueError("Oturum bulunamadı veya süresi doldu.")

        ctx = self.sessions[task_id]
        ctx.last_seen = time.monotonic()
        
        # Add target message to history
        self.add_message(task_id, "target", target_message)
        
        # Build prompt
        history_str = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in ctx.history])
        
        prompt = f"""
SEN BİR DİJİTAL PSİKOLOJİK HARP VE SOSYAL MÜHENDİSLİK YAPAY ZEKASISIN (PINEAL-HERETIC v{VERSION}).
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
        
        # Add our response to history
        self.add_message(task_id, "agent", response.next_move)
        
        return response
