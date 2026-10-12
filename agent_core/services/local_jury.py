"""FAZ D · D2 — YEREL JÜRİ: aynı kanıt, birden çok yerel kafada bağımsız oylanır.

Neden: panel kararı bugüne dek ya tek zincire ya da UZAK modellere bağlıydı.
Uzak jüri iki şeyi bedavaya vermez: (a) maliyet sıfır değildir, (b) hedef verisi
makineden çıkar. Bu modül aynı çapraz jüri fikrini **yerel modellerde** koşar:

    * Koltuk = AYRI bir yerel model (``PINEAL_JURY_LOCAL_MODELS``). Aynı modeli
      iki kez saymak bağımsızlık değildir; tekrarlar düşürülür ve raporlanır.
    * Uç YALNIZ yereldir (``127.0.0.1`` / ``localhost`` / ``[::1]``); uzak adres
      ``non_local_endpoint`` ile REDDEDİLİR. Uzağa SESSİZCE düşülmez — bu
      modül uzak modele hiç bağlanmaz (llm_gateway'e dokunmaz).
    * Oy sözlüğü TEK kaynaktan gelir (``services/jury_consensus``); kapalı
      sözlük dışı kelime OY SAYILMAZ, ``sozluk_disi`` olarak raporlanır.
    * Karar kuralı açıkça yazılır: ``oy_birligi`` · ``cokluk`` · ``berabere`` ·
      ``gecerli_oy_yok`` · ``tek_koltuk``. Çoğunluk, YETER SAYIYI (``jury_consensus.quorum``)
      karşılamıyorsa ``consensus=False`` olur: azınlıkla "karar" iddia edilmez.
    * Koltuk hatası sessizce yutulmaz: hangi koltuk neden oy veremedi, kanıtta durur.

Çıktı KANITTIR ama ``inference``dır: jüri hükmü bir model yargısıdır, gözlem
değildir. Bu ayrım kanıt zarfında (``epistemic_type``) açıkça taşınır.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Sequence
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

# Oy sözlüğü KOPYALANMAZ: tek doğruluk kaynağı B1 denetçisidir.
from agent_core.services.jury_consensus import (
    VOTE_CONTRADICTED,
    VOTE_FALSE,
    VOTE_UNKNOWN,
    VOTE_VERIFIED,
    quorum,
)

__all__ = [
    "GATE",
    "DEFAULT_SEATS",
    "MAX_SEATS",
    "VOICE_VOCABULARY",
    "SeatVote",
    "LocalJuryVerdict",
    "local_endpoint",
    "seat_models",
    "availability",
    "status",
    "evaluate",
]

#: Yetenek kapısı (PolicyKernel ENABLE_* sözlüğü).
GATE = "ENABLE_LOCAL_JURY"

DEFAULT_SEATS = 3
MAX_SEATS = 5

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"})

#: Modele kabul ettirilen kapalı sözlük + dürüst eşanlamlı haritası. Eşanlamlılar
#: modele "yakın kelimeyi kabul et" demek için değil, İngilizce yanıt veren yerel
#: modellerin YALNIZ bu karşılıklarla sayılması içindir; başka her kelime geçersizdir.
VOICE_VOCABULARY: dict[str, str] = {
    VOTE_VERIFIED.lower(): VOTE_VERIFIED,
    VOTE_CONTRADICTED.lower(): VOTE_CONTRADICTED,
    VOTE_FALSE.lower(): VOTE_FALSE,
    VOTE_UNKNOWN.lower(): VOTE_UNKNOWN,
    "verified": VOTE_VERIFIED,
    "supported": VOTE_VERIFIED,
    "contradicted": VOTE_CONTRADICTED,
    "false": VOTE_FALSE,
    "unknown": VOTE_UNKNOWN,
    "bilinmiyor": VOTE_UNKNOWN,
}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class SeatVote(BaseModel):
    """Tek koltuğun oyu (ham çıktı ve hüküm ayrı ayrı görünür)."""

    model: str
    vote: str = VOTE_UNKNOWN      # sayılan (kanonik) oy
    raw_vote: str = ""            # modelin yazdığı ham kelime
    reason: str = ""
    confidence: float | None = None
    latency_ms: int = 0
    error: str = ""               # koltuk oy veremediyse SEBEP (sessiz yutma yok)

    model_config = ConfigDict(extra="forbid")


class LocalJuryVerdict(BaseModel):
    """Jürinin tek kararı — kimse kendi başına 'konsensüs' ilan edemez."""

    available: bool = False
    reason: str = ""              # available=False ise makine-okunur sebep
    verdict: str = VOTE_UNKNOWN
    rule: str = ""                # oy_birligi · cokluk · berabere · gecerli_oy_yok · tek_koltuk
    consensus: bool = False
    seats_run: int = 0
    counted: int = 0              # sözlük içi oy sayısı
    quorum_required: int = 1
    tally: dict[str, int] = Field(default_factory=dict)
    dissent: list[str] = Field(default_factory=list)
    votes: list[SeatVote] = Field(default_factory=list)
    duplicates_removed: list[str] = Field(default_factory=list)
    endpoint: str = ""
    machine_note: str = ""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# yapılandırma (yerellik tartışmasız)
# --------------------------------------------------------------------------- #
def local_endpoint() -> tuple[str, str]:
    """(taban adres, '') ya da ('', sebep). YALNIZ yerel jüri ucu kabul edilir.

    Ortam TEK kaynaktan okunur (``os.environ``): ``jury_consensus.quorum()`` de
    süreç ortamını okur; enjekte edilebilir ikinci bir env sözlüğü sapma
    üretiyordu (test yakaladı). Testler ``monkeypatch.setenv`` kullanır.
    """
    source = os.environ
    raw = (
        source.get("PINEAL_JURY_LOCAL_URL")
        or source.get("LOCAL_LLM_URL")
        or "http://127.0.0.1:11434/v1"
    ).strip().rstrip("/")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return "", "non_local_endpoint"
    if parsed.scheme not in {"http", "https"}:
        return "", "bad_endpoint_scheme"
    return raw, ""


def seat_models() -> tuple[list[str], list[str]]:
    """(koltuk modelleri, düşürülen tekrarlar).

    Tekrar eden model adı ikinci koltuk SAYILMAZ: aynı ağırlıklar bağımsız oy
    vermez. Listenin sırası korunur (determinizm), tavan ``MAX_SEATS``tir.
    """
    source = os.environ
    raw = (source.get("PINEAL_JURY_LOCAL_MODELS") or "").strip()
    if not raw:
        fallback = (source.get("LOCAL_LLM_MODEL") or "").strip()
        raw = fallback
    names = [part.strip() for part in raw.split(",") if part.strip()]
    try:
        seats = max(1, int((source.get("PINEAL_JURY_SEATS") or str(DEFAULT_SEATS)).strip()))
    except ValueError:
        seats = DEFAULT_SEATS
    seats = min(seats, MAX_SEATS)

    unique: list[str] = []
    duplicates: list[str] = []
    for name in names:
        if name in unique:
            duplicates.append(name)
            continue
        unique.append(name)
    return unique[:seats], duplicates


def availability() -> tuple[bool, str]:
    """(kullanılabilir mi, sebep). Sebep makine-okunurdur, uydurma uygunluk yok."""
    _, reason = local_endpoint()
    if reason:
        return False, reason
    models, _ = seat_models()
    if not models:
        return False, "no_local_models"
    return True, ""


def status() -> dict[str, Any]:
    """Kokpit/telemetri için dürüst durum (uç yerel mi, kaç bağımsız koltuk)."""
    url, reason = local_endpoint()
    models, duplicates = seat_models()
    available, availability_reason = availability()
    return {
        "available": available,
        "reason": reason or availability_reason or None,
        "gate": GATE,
        "endpoint": url or None,
        "models": models,
        "seats": len(models),
        "independent_seats": len(models) >= 2,
        "duplicates_removed": duplicates,
        "quorum": quorum(),
        "max_seats": MAX_SEATS,
        "note": (
            "tek model tanımlı: oy sayılır ama 'konsensüs' İLAN EDİLMEZ"
            if len(models) == 1
            else ""
        ),
    }


# --------------------------------------------------------------------------- #
# oy toplama (ağ: YALNIZ yerel uç)
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = (
    "Sen bağımsız bir doğrulama jürisi koltuğusun. Sana verilen İDDİA ve KANIT "
    "metnini değerlendir. Yalnız şu dört kelimeden biriyle oy ver: "
    "DOĞRULANDI, ÇELİŞKİLİ, YALAN, BİLİNMİYOR. "
    "Cevabın SADECE JSON olsun: "
    '{"vote": "<kelime>", "confidence": <0..1>, "reason": "<kısa gerekçe>"}'
)


def _extract_payload(text: str) -> dict[str, Any] | None:
    """Modelin çıktısından JSON nesnesini çıkarır; bulamazsa None (uydurma yok)."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    candidates = [stripped]
    match = _JSON_BLOCK_RE.search(stripped)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _canonical_vote(raw: Any) -> str | None:
    """Ham kelimeyi kapalı sözlüğe çevirir; sözlük dışıysa None."""
    if not isinstance(raw, str):
        return None
    return VOICE_VOCABULARY.get(raw.strip().lower())


async def _ask_seat(
    client,
    endpoint: str,
    model: str,
    claim: str,
    evidence_text: str,
    *,
    timeout: float,
) -> SeatVote:
    """Tek koltuk: yerel OpenAI-uyumlu uçtan oy ister. Hata = dürüst koltuk hatası."""
    started = time.perf_counter()
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"İDDİA:\n{claim}\n\nKANIT:\n{evidence_text}\n\nJSON cevap:",
            },
        ],
    }
    try:
        response = await client.post(f"{endpoint}/chat/completions", json=payload, timeout=timeout)
    except Exception as exc:
        return SeatVote(
            model=model,
            error=f"seat_request_failed:{type(exc).__name__}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return SeatVote(model=model, error=f"seat_status:{response.status_code}", latency_ms=latency)
    try:
        body = response.json()
    except ValueError:
        return SeatVote(model=model, error="seat_bad_json", latency_ms=latency)
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return SeatVote(model=model, error="seat_bad_shape", latency_ms=latency)

    parsed = _extract_payload(str(content))
    if parsed is None:
        return SeatVote(
            model=model, raw_vote=str(content)[:80], error="seat_unparseable", latency_ms=latency
        )
    raw_vote = str(parsed.get("vote", ""))
    vote = _canonical_vote(raw_vote)
    if vote is None:
        return SeatVote(
            model=model, raw_vote=raw_vote[:40], error="sozluk_disi", latency_ms=latency
        )
    confidence: float | None = None
    try:
        if parsed.get("confidence") is not None:
            confidence = max(0.0, min(1.0, float(parsed["confidence"])))
    except (TypeError, ValueError):
        confidence = None
    return SeatVote(
        model=model,
        vote=vote,
        raw_vote=raw_vote[:40],
        reason=str(parsed.get("reason", ""))[:200],
        confidence=confidence,
        latency_ms=latency,
    )


def _aggregate(votes: Sequence[SeatVote], *, duplicates: list[str], endpoint: str) -> LocalJuryVerdict:
    """Oy sayımı — kural açıkça yazılır, azınlıkla 'karar' ilan edilmez."""
    counted = [vote for vote in votes if not vote.error and vote.vote]
    tally: dict[str, int] = {}
    for vote in counted:
        tally[vote.vote] = tally.get(vote.vote, 0) + 1

    required = quorum()
    verdict = LocalJuryVerdict(
        available=True,
        seats_run=len(votes),
        counted=len(counted),
        quorum_required=required,
        tally=tally,
        votes=list(votes),
        duplicates_removed=duplicates,
        endpoint=endpoint,
    )

    if not counted:
        verdict.rule = "gecerli_oy_yok"
        verdict.verdict = VOTE_UNKNOWN
        verdict.machine_note = "hiçbir koltuk sözlük içi oy veremedi — karar İDDİA EDİLMEZ"
        return verdict

    if len(counted) == 1:
        verdict.rule = "tek_koltuk"
        verdict.verdict = counted[0].vote
        verdict.consensus = False
        verdict.machine_note = "tek geçerli oy: karar o koltuktan gelir, konsensüs DEĞİLDİR"
        return verdict

    # Kazanan oy: en çok sayılan; beraberlikte BİLİNMİYOR (uydurma kırılma yok).
    ranked = sorted(tally.items(), key=lambda pair: (-pair[1], pair[0]))
    top_vote, top_count = ranked[0]
    tie = len(ranked) > 1 and ranked[1][1] == top_count
    if tie:
        verdict.rule = "berabere"
        verdict.verdict = VOTE_UNKNOWN
        verdict.consensus = False
        verdict.machine_note = "oylar berabere — BİLİNMİYOR (kırılma uydurulmaz)"
    else:
        verdict.verdict = top_vote
        unanimous = top_count == len(counted) and len(counted) == len(votes)
        verdict.rule = "oy_birligi" if unanimous else "cokluk"
        verdict.consensus = top_count >= required
        if not verdict.consensus:
            verdict.machine_note = (
                f"çoğunluk var ama yeter sayı ({required}) karşılanmadı — konsensüs değil"
            )
    verdict.dissent = sorted(vote.model for vote in counted if vote.vote != verdict.verdict)
    return verdict


async def evaluate(
    claim: str,
    evidence_text: str,
    *,
    timeout: float = 60.0,
) -> LocalJuryVerdict:
    """İddiayı yerel jüriye sorar. Motor yoksa KARAR UYDURULMAZ (available=False)."""
    endpoint, reason = local_endpoint()
    if not endpoint:
        return LocalJuryVerdict(available=False, reason=reason)
    models, duplicates = seat_models()
    if not models:
        return LocalJuryVerdict(available=False, reason="no_local_models")
    claim_text = (claim or "").strip()
    evidence = (evidence_text or "").strip()
    if not claim_text:
        return LocalJuryVerdict(available=False, reason="empty_claim")
    if not evidence:
        return LocalJuryVerdict(available=False, reason="empty_evidence")

    try:
        import httpx
    except ImportError:
        return LocalJuryVerdict(available=False, reason="dependency_missing:httpx")

    async with httpx.AsyncClient() as client:
        # [E7-muaf] `_ask_seat` ağ/JSON/şekil hatalarını yakalayıp
        # SeatVote(error=...) döner — düşen koltuk jüriyi düşürmez, karar
        # `quorum`/hata sayımıyla dürüstçe raporlanır.
        votes = await asyncio.gather(
            *(
                _ask_seat(client, endpoint, model, claim_text, evidence, timeout=timeout)
                for model in models
            )
        )
    return _aggregate(votes, duplicates=duplicates, endpoint=endpoint)
