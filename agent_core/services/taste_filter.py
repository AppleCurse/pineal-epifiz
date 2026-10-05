"""FAZ C · C1 — JENERİK YANIT FİLTRESİ ("laf salatası düşer").

Röntgen bulgusu: Aspasia'nın DİLİ bir prompt umuduna bağlıydı — "iyi prompt
yazarsak iyi konuşur". Koddaki tek gerçek: sistem prompt'u. Jenerik yanıt
("Tabii ki! Kesinlikle harika bir soru, size şöyle yardımcı olabilirim...")
AYNEN kullanıcıya gidiyordu; ne ölçen ne düşüren bir katman vardı.

Bu modül o katman:

1.  **Ölçüm:** her yanıt deterministik sinyallerle tartılır (jenerik açılış,
    kalıp sorumluluk reddi, soruyu geri atma, kaçamak/ dolgu yoğunluğu,
    TEKRAR, uzun ama boş, emoji, ve **en önemlisi**: elde VERİ varken yanıtın
    o veriye hiç dokunmaması).
2.  **Düşürme:** jeneriklik eşiği aşarsa yanıt KULLANICIYA ÇIKMAZ; yerine
    kanıttan derlenmiş tek cümlelik dürüst yanıt konur (veri yoksa "yok" denir,
    uydurulmaz).
3.  **İz:** düşen her yanıt telemetriye yazılır (`memory/telemetry/taste.jsonl`)
    — operatör NEYİN düştüğünü ve NEDEN düştüğünü görür.
4.  **Eşik:** jeneriklik eşiği de kalibrasyon kapsamıdır (`taste`): ölçülmeden
    değişmez, elle sabitlenebilir (B5 ile aynı kural).

LLM çağrısı yok, ağ yok, rastgelelik yok: aynı metin -> aynı hüküm.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field

#: Kalibrasyon kapsamı (threshold_calibration ile aynı eşik disiplini).
SCOPE_TASTE = "taste"

DEFAULT_TASTE_THRESHOLD = 0.70

_SENTENCE_SPLIT = re.compile(r"[.!?…\n]+")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

GENERIC_OPENERS = (
    "tabii ki", "elbette", "kesinlikle", "hiç şüphesiz", "harika bir soru",
    "çok güzel bir soru", "genel olarak", "her şey yolunda", "merak etme",
    "of course", "certainly", "absolutely", "great question", "sure thing",
)
BOILERPLATE = (
    "bir yapay zeka olarak", "bir yapay zekâ olarak", "yapay zeka modeliyim",
    "dil modeliyim", "as an ai", "as a language model", "i am just an ai",
)
BOUNCE = (
    "nasıl yardımcı olabilirim", "nasıl yardımcı olabilirim?", "daha fazla bilgi ver",
    "daha detaylı bilgi", "daha fazla ayrıntı", "bilgi verirsen",
    "how can i help", "let me know if", "would you like me to",
)
HEDGES = (
    "belki", "muhtemelen", "sanırım", "galiba", "olabilir", "gibi görünüyor",
    "gibi duruyor", "tahminim", "maybe", "perhaps", "probably", "might", "could be",
)
FILLERS = (
    "çok önemli", "oldukça", "gerçekten", "kesinlikle", "yani", "işte",
    "aslında", "tabii", "şüphesiz", "gayet", "fevkalade",
    "very important", "really", "truly", "absolutely",
)
EVIDENCE_WORDS = (
    "kanıt", "görev", "ajan", "durum", "veri", "telemetri", "hüküm", "ölçüm",
    "yüzde", "%", "task", "evidence", "status",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _tokens(text: str) -> List[str]:
    return [t for t in _WORD_RE.findall(str(text or "").lower()) if len(t) > 1]


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(str(text or "")) if len(s.strip()) > 3]


def threshold(default: float = DEFAULT_TASTE_THRESHOLD) -> float:
    """Jeneriklik eşiği: kalibrasyondan gelir (ölçülmeden değişmez)."""
    from agent_core.services.threshold_calibration import resolved_threshold

    return resolved_threshold(SCOPE_TASTE, default=default).value


class TasteVerdict(BaseModel):
    """Bir yanıtın jeneriklik tartısı — gerekçeleriyle (gizli skor yok)."""

    available: bool = False
    generic: bool = False
    generic_score: float = 0.0
    threshold: float = DEFAULT_TASTE_THRESHOLD
    reasons: List[str] = Field(default_factory=list)
    signals: Dict[str, float] = Field(default_factory=dict)
    word_count: int = 0
    machine_note: str = ""

    model_config = ConfigDict(extra="forbid")


class TasteDecision(BaseModel):
    """Filtre kararı: metin geçti mi, geçmediyse ne konuldu?"""

    message: str = ""
    kept: bool = True
    reason: str = ""
    verdict: TasteVerdict = Field(default_factory=TasteVerdict)

    model_config = ConfigDict(extra="forbid")


def score_response(text: str, *, context: Optional[Dict[str, Any]] = None) -> TasteVerdict:
    """Yanıtı jeneriklik açısından TARTAR (deterministik; LLM yok)."""
    raw = str(text or "")
    blob = _norm(raw)
    verdict = TasteVerdict()
    if len(blob) < 3:
        verdict.machine_note = "TASTE: yanıt boş — tartılamaz."
        return verdict

    words = _tokens(blob)
    sentences = _sentences(raw)
    word_count = max(1, len(words))
    signals: Dict[str, float] = {}
    reasons: List[str] = []

    def _hit(phrases: Iterable[str]) -> int:
        return sum(1 for phrase in phrases if phrase in blob)

    openers = _hit(GENERIC_OPENERS)
    if openers:
        signals["jenerik_acilis"] = round(min(0.18, 0.12 * openers), 4)
        reasons.append(f"jenerik açılış x{openers}")

    boiler = _hit(BOILERPLATE)
    if boiler:
        signals["kalip_red"] = 0.25
        reasons.append("kalıp sorumluluk reddi")

    bounce = _hit(BOUNCE)
    if bounce:
        signals["soruyu_geri_atma"] = round(min(0.20, 0.14 * bounce), 4)
        reasons.append("soruyu geri atıyor (boş nezaket)")

    hedges = _hit(HEDGES)
    if hedges >= 3 or (word_count and hedges / word_count * 100 >= 3):
        signals["kacamak_yogunluk"] = 0.12
        reasons.append(f"kaçamak ifade x{hedges}")

    fillers = _hit(FILLERS)
    if word_count and fillers / word_count * 100 >= 3:
        signals["dolgu_yogunluk"] = 0.10
        reasons.append(f"dolgu kelime x{fillers}")

    if len(sentences) >= 2:
        unique = {_norm(s) for s in sentences}
        if len(unique) < len(sentences):
            signals["tekrar"] = 0.15
            reasons.append("aynı cümle tekrar ediyor")

    if word_count >= 120:
        lexical = len(set(words)) / word_count
        if lexical < 0.45:
            signals["uzun_bos"] = 0.10
            reasons.append(f"uzun ama boş (özgünlük {lexical:.2f})")

    emojis = sum(1 for ch in raw if ch in "😀😁😂🤣😊😍🤔👍🙏✨🎉💡🔥💯🙂🙃")
    if emojis >= 2:
        signals["emoji"] = round(min(0.08, 0.04 * emojis), 4)
        reasons.append(f"emoji x{emojis}")

    # EN AĞIR SİNYAL: elde VERİ var, yanıt ona hiç dokunmuyor.
    context_blob = _norm(" ".join(str(v or "") for v in (context or {}).values()))
    context_has_data = bool(re.search(r"\d", context_blob)) and len(context_blob) >= 40
    if context_has_data and not any(word in blob for word in EVIDENCE_WORDS):
        signals["veri_kullanilmadi"] = 0.22
        reasons.append("elde veri var, yanıt ona değinmiyor")

    total = round(min(1.0, sum(signals.values())), 4)
    verdict.available = True
    verdict.generic_score = total
    verdict.signals = signals
    verdict.reasons = reasons
    verdict.word_count = word_count
    verdict.machine_note = (
        f"TASTE: jeneriklik {total:.2f}"
        + (f" · {', '.join(reasons[:3])}" if reasons else " · temiz")
    )
    return verdict


def _deterministic_reply(context: Optional[Dict[str, Any]]) -> str:
    """Jenerik yanıt DÜŞTÜĞÜNDE yerine konan dürüst cümle (kanıttan)."""
    digest = str((context or {}).get("verdict") or "").strip()
    if digest:
        first = digest.strip().splitlines()[0]
        return f"Mösyö, lafı dolandırmayayım: {first}"
    telemetry = str((context or {}).get("telemetry") or "").strip()
    if telemetry:
        first = telemetry.strip().splitlines()[0]
        return f"Mösyö, ölçülen durum şu: {first}"
    return "Mösyö, bu soruya düşecek doğrulanmış veri yok; uydurmayacağım."


def filter_response(
    text: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    threshold_override: Optional[float] = None,
    record_telemetry: bool = True,
) -> TasteDecision:
    """Yanıtı süz geçir: jenerikse DÜŞÜR, yerine kanıt cümlesi koy."""
    limit = threshold() if threshold_override is None else float(threshold_override)
    verdict = score_response(text, context=context)
    verdict.threshold = round(limit, 4)
    verdict.generic = verdict.available and verdict.generic_score >= limit

    if not verdict.generic:
        return TasteDecision(message=str(text or ""), kept=True, reason="", verdict=verdict)

    decision = TasteDecision(
        message=_deterministic_reply(context),
        kept=False,
        reason="jenerik_yanit",
        verdict=verdict,
    )
    if record_telemetry:
        log_decision(text, decision)
    return decision


# ------------------------------------------------------------------- telemetri
def telemetry_path(storage: Optional[str] = None) -> str:
    base = storage or os.getenv("PINEAL_TELEMETRY_DIR") or os.path.join("memory", "telemetry")
    return os.path.join(base, "taste.jsonl")


def log_decision(text: str, decision: TasteDecision, storage: Optional[str] = None) -> bool:
    """Düşen yanıtı telemetriye yazar (yalnız ölçü + kırpık alıntı, pipeline bozulmaz)."""
    if os.getenv("PINEAL_TASTE_LOG", "true").strip().lower() not in {"1", "true", "yes", "on", "açık"}:
        return False
    row = {
        "recorded_at": round(time.time(), 3),
        "kept": decision.kept,
        "reason": decision.reason,
        "score": decision.verdict.generic_score,
        "threshold": decision.verdict.threshold,
        "reasons": decision.verdict.reasons,
        "signals": decision.verdict.signals,
        "word_count": decision.verdict.word_count,
        "excerpt": re.sub(r"\s+", " ", str(text or ""))[:200],
    }
    try:
        path = telemetry_path(storage)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def telemetry_summary(storage: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Operatörün göreceği özet: kaç yanıt düştü, neden düştü."""
    path = telemetry_path(storage)
    rows: List[Dict[str, Any]] = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
        except (OSError, ValueError):
            rows = []
    dropped = [r for r in rows if not r.get("kept")]
    reasons: Dict[str, int] = {}
    for row in dropped:
        for reason in row.get("reasons") or []:
            reasons[reason] = reasons.get(reason, 0) + 1
    mean = round(sum(float(r.get("score") or 0.0) for r in rows) / len(rows), 4) if rows else 0.0
    return {
        "schema_version": "taste-telemetry-v1",
        "scope": SCOPE_TASTE,
        "threshold": threshold(),
        "total": len(rows),
        "dropped": len(dropped),
        "mean_score": mean,
        "top_reasons": sorted(reasons.items(), key=lambda kv: -kv[1])[:8],
        "recent": rows[-max(0, limit):],
        "machine_note": (
            f"TASTE: {len(dropped)}/{len(rows)} yanıt jenerik bulundu · eşik {threshold():.2f}"
        ),
    }
