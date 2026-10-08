"""FAZ D · D4 — DİL TESPİTİ: deterministik, modelsiz, ağsız.

Sözleşme:
    * Yazı sistemi Unicode aralıklarından ÖLÇÜLÜR (tahmin yok).
    * Dil puanı, karakter işaretleri + durma sözcüklerinden hesaplanır.
    * Model YOKTUR, ağ YOKTUR: aynı metin her zaman aynı sonucu verir.
    * Sinyal yoksa ETİKET UYDURULMAZ: ``language="unknown"`` + makine-okunur
      sebep (``too_short`` / ``no_signal`` / ``script_unsupported:<script>``).
    * Güven skoru dürüsttür: tr/az gibi birbirine çok yakın dillerde marj
      küçülür ve güven ~0.50'ye iner; 0.99 diye ŞİŞİRİLMEZ.

Kapsam (ölçülen diller): tr · en · de · es · fr · ru · az.
Kapsam dışı yazı sistemleri (Arap, CJK, İbrani, Yunan…) tespit EDİLİR ama
dil etiketi verilmez — sebep yazılır.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LanguageFinding",
    "detect_language",
    "record_finding",
    "last_finding",
    "reset_last_finding",
    "SUPPORTED_LANGUAGES",
]

#: Bu modülün puanlayabildiği diller (tek kaynak — ikinci liste yok).
SUPPORTED_LANGUAGES = ("tr", "en", "de", "es", "fr", "ru", "az")

#: Alfabe karakteri eşiği: altındaki metinde dil sinyali ölçülemez.
MIN_LETTERS = 12

#: Yazı sistemi payı bu oranın altındaysa "mixed" sayılır (kararsız metin).
SCRIPT_DOMINANCE = 0.60

_TOKEN_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*", re.UNICODE)


class LanguageFinding(BaseModel):
    """Bir metnin ölçülmüş dil bulgusu (uydurma alan yok)."""

    language: str = "unknown"
    confidence: float = 0.0
    script: str = ""
    reason: Optional[str] = None
    signals: Dict[str, float] = Field(default_factory=dict)
    chars: int = 0

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# DURMA SÖZCÜKLERİ — ayrıştırıcılığı yüksek, kısa ve sık sözcükler.
# ---------------------------------------------------------------------------

def _stop(*words: str) -> frozenset:
    """Durma sözcüğü kümesi: kesme işaretleri iki tarafta da aynı katlanır."""
    out = set()
    for word in words:
        folded = word.replace("'", "").replace("’", "").strip()
        if folded:
            out.add(folded)
    return frozenset(out)


_STOPWORDS: Dict[str, frozenset] = {
    "tr": _stop(
        *"""ve bir için ile ama çok bu şu değil mi mı ben sen biz siz onlar ne nasıl neden
        bugün yarın var yok gibi kadar daha en olarak olan evet hayır teşekkür lütfen
        merhaba günaydın iyi kötü yeni eski her bazı bütün sonra önce şimdi burada orada
        diye göre karşı rağmen çünkü ancak fakat ise ya veya hem neyse""".split()
    ),
    "az": _stop(
        *"""və bir üçün ilə amma çox bu deyil mən sən biz siz onlar nə necə niyə
        sabah var yox kimi qədər daha ən olan olaraq bəli xeyr təşəkkür
        hər yalnız əgər həm sonra indi burada orada çünki ancaq lakin isə də
        yaxud yeni köhnə yaxşı pis""".split()
    ),
    "en": _stop(
        *"""the and for with this that have has not you your are was were will would
        can could what when where why how today tomorrow yes no please thanks hello
        good morning about from they them their there here very just some been being
        because but also then than only into over after before while which who""".split()
    ),
    "de": _stop(
        *"""und der die das für mit nicht ein eine ist sind war wird haben werden sie
        ich du wir ihr was wann wo warum wie heute morgen ja nein bitte danke hallo
        gut sehr auch aber wenn dann hier dort von zu auf nur noch schon weil oder
        wenn bei nach aus über unter kann könnte muss""".split()
    ),
    "es": _stop(
        *"""el la los las para con está son era fue será usted qué cuándo dónde cómo
        hoy mañana gracias hola bueno muy pero cuando donde desde hasta también hay
        uno una unos unas ese esa esto esta porque aunque mientras quien quienes sí
        nosotros vosotros ellos ellas tu su mis tus nuestros""".split()
    ),
    "fr": _stop(
        *"""le la les un une des et pour avec ne pas est sont était sera vous tu je
        nous que quoi quand pourquoi comment aujourd'hui demain oui non merci bonjour
        très mais si aussi ici là dans sur parce bien tout tous toute toutes
        sans chez entre vers après avant pendant ils elles il elle""".split()
    ),
    "ru": _stop(
        *"""и в на с по не что это как но из за для был была было будут есть вы ты я
        мы они он она когда где почему сегодня завтра да нет спасибо привет хорошо
        очень если или тоже здесь там только ещё уже потому чтобы этого этой этот
        были быть его её их вам вас нас""".split()
    ),
}

#: Ayırt edici karakter işaretleri: (karakter, ağırlık). Paylaşılan karakterler
#: düşük, dile özgü karakterler (ör. az 'ə', de 'ß', es 'ñ') yüksek ağırlıklı.
_CHAR_MARKERS: Dict[str, Dict[str, float]] = {
    "tr": {"ğ": 3.0, "ş": 2.0, "ı": 2.5, "İ": 1.5, "ç": 0.5, "ö": 0.3, "ü": 0.3},
    "az": {"ə": 4.0, "ğ": 2.0, "ş": 1.5, "ı": 1.5, "ç": 0.5, "ö": 0.3, "ü": 0.3},
    "de": {"ß": 4.0, "ä": 2.0, "ö": 0.8, "ü": 0.6},
    "es": {"ñ": 4.0, "¿": 4.0, "¡": 4.0, "á": 1.0, "í": 0.8, "ó": 0.8, "ú": 0.8, "é": 0.4},
    "fr": {"é": 1.2, "è": 2.0, "ê": 2.0, "ë": 1.5, "à": 1.2, "â": 2.0, "ù": 1.5, "û": 2.0, "œ": 3.0, "ç": 1.0},
    "en": {},
    "ru": {"ы": 2.0, "э": 2.0, "ъ": 2.5, "ё": 2.5, "щ": 1.5, "ж": 1.0, "ш": 0.8},
}

#: Mutlak sinyal eşiği: en iyi dilin puanı bunun altındaysa etiket verilmez.
MIN_SIGNAL = 0.012

#: Güvenin doyduğu marj değeri (marj >= 1.0 sayılır).
_MARGIN_FULL = 0.65


# ---------------------------------------------------------------------------
# YAZI SİSTEMİ — Unicode aralıklarından ölçüm.
# ---------------------------------------------------------------------------


def _script_of(ch: str) -> str:
    code = ord(ch)
    if 0x0400 <= code <= 0x052F:
        return "cyrillic"
    if (0x0041 <= code <= 0x007A) or (0x00C0 <= code <= 0x024F):
        return "latin"
    if 0x0600 <= code <= 0x06FF:
        return "arabic"
    if 0x4E00 <= code <= 0x9FFF:
        return "cjk"
    if 0x0370 <= code <= 0x03FF:
        return "greek"
    if 0x0590 <= code <= 0x05FF:
        return "hebrew"
    if 0x3040 <= code <= 0x30FF:
        return "japanese"
    if 0xAC00 <= code <= 0xD7AF:
        return "hangul"
    return "other"


def _dominant_script(letters: list) -> tuple:
    """(baskın yazı sistemi, payı) — pay SCRIPT_DOMINANCE altındaysa 'mixed'."""
    counts: Dict[str, int] = {}
    for ch in letters:
        counts[_script_of(ch)] = counts.get(_script_of(ch), 0) + 1
    if not counts:
        return "none", 0.0
    top, hits = max(counts.items(), key=lambda kv: kv[1])
    share = hits / len(letters)
    if top == "other":
        return "unknown", share
    return (top, share) if share >= SCRIPT_DOMINANCE else ("mixed", share)


# ---------------------------------------------------------------------------
# PUANLAMA
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list:
    raw = _TOKEN_RE.findall(text)
    out = []
    for tok in raw:
        folded = tok.casefold().replace("'", "").replace("’", "")
        if folded:
            out.append(folded)
    return out


def _score_languages(text: str, tokens: list, letters: int) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for lang in SUPPORTED_LANGUAGES:
        stops = _STOPWORDS[lang]
        hits = sum(1 for tok in tokens if tok in stops)
        stop_rate = hits / max(len(tokens), 1)
        char_rate = 0.0
        markers = _CHAR_MARKERS.get(lang) or {}
        if markers and letters:
            weighted = 0.0
            for ch, weight in markers.items():
                weighted += text.count(ch) * weight
                low = ch.lower()
                if len(low) == 1 and low != ch:
                    weighted += text.count(low) * weight
            char_rate = weighted / letters
        scores[lang] = stop_rate + char_rate
    return scores


def _confidence(top: float, second: float, tokens: int) -> float:
    """Dürüst güven: marj + mutlak sinyal + örneklem bolluğu. Şişirme YOK.

    Üç çarpan da 0..1 aralığındadır:
        marj     — birinci ile ikinci dil arasındaki fark,
        sinyal   — en iyi dilin mutlak puanı (zayıf sinyal güven alamaz),
        bolluk   — örneklem büyüklüğü (3 sözcüklük metin 0.99 güven ALAMAZ).
    """
    if top <= 0:
        return 0.0
    margin = (top - second) / top
    strength = min(1.0, top / 0.06)
    abundance = min(1.0, max(tokens, 0) / 8.0)
    conf = 0.5 + 0.49 * min(1.0, margin / _MARGIN_FULL) * strength * abundance
    return round(min(0.99, max(0.5, conf)), 2)


def detect_language(text: str) -> LanguageFinding:
    """Metnin dilini ölçer (deterministik). Sinyal yoksa 'unknown' + sebep."""
    raw = str(text or "")
    letters_list = [c for c in raw if c.isalpha()]
    chars = len(raw.strip())
    if len(letters_list) < MIN_LETTERS:
        return LanguageFinding(language="unknown", script="", reason="too_short", chars=chars)

    script, share = _dominant_script(letters_list)

    if script == "cyrillic":
        tokens = _tokens(raw)
        scores = _score_languages(raw, tokens, len(letters_list))
        top_score = scores["ru"]
        if top_score < MIN_SIGNAL:
            return LanguageFinding(
                language="unknown", script="cyrillic", reason="no_signal",
                signals={"ru": round(top_score, 4)}, chars=chars,
            )
        # Kiril tek dille puanlanır (ru); güven sinyal + örneklem bolluğundan gelir.
        strength = min(1.0, top_score / 0.08)
        abundance = min(1.0, len(tokens) / 8.0)
        conf = round(min(0.99, max(0.5, 0.5 + 0.49 * strength * abundance)), 2)
        return LanguageFinding(
            language="ru", confidence=conf, script="cyrillic",
            signals={"ru": round(top_score, 4)}, chars=chars,
        )

    if script != "latin":
        return LanguageFinding(
            language="unknown", script=script, reason=f"script_unsupported:{script}",
            chars=chars,
        )

    tokens = _tokens(raw)
    scores = _score_languages(raw, tokens, len(letters_list))
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_lang, top_score = ranked[0]
    second_lang, second_score = ranked[1]

    if top_score < MIN_SIGNAL:
        return LanguageFinding(
            language="unknown", script="latin", reason="no_signal",
            signals={lang: round(s, 4) for lang, s in ranked[:3]}, chars=chars,
        )

    conf = _confidence(top_score, second_score, len(tokens))
    return LanguageFinding(
        language=top_lang,
        confidence=conf,
        script="latin",
        signals={lang: round(s, 4) for lang, s in ranked},
        chars=chars,
    )


# ---------------------------------------------------------------------------
# KOKPİT PİLİ: kanıta işlenen SON ölçüm (uydurma değil, gerçek tespit).
# ---------------------------------------------------------------------------

_LAST: Dict[str, Any] = {}


def record_finding(finding: LanguageFinding, *, source_engine: str, url: str = "") -> None:
    """Web çıkarıcıların ölçtüğü dili kokpit pili için saklar."""
    from datetime import datetime, timezone

    _LAST.clear()
    _LAST.update(
        {
            "language": finding.language,
            "confidence": finding.confidence,
            "script": finding.script,
            "reason": finding.reason,
            "chars": finding.chars,
            "source_engine": source_engine,
            "url": url,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )


def last_finding() -> Optional[Dict[str, Any]]:
    """Son ölçüm; hiç ölçüm yapılmadıysa None (pil 'ÖLÇÜLMEDİ' gösterir)."""
    return dict(_LAST) if _LAST else None


def reset_last_finding() -> None:
    """Yalnız testler için."""
    _LAST.clear()
