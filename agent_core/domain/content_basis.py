"""P0 · KANIT TİPİ AYRIMI — "gönderi" ile "arama sonucu" AYNI ŞEY DEĞİLDİR.

Neden (denetim 2026-10-16 · Bulgu 2):
    Web dosyası (open-source dossier) yolu, arama motorundan gelen 3-5 satırlık
    snippet'ı ``target_profile.posts`` alanına yazıyordu. Sonuç: 9 tüketici
    (4 ajan + 3 deterministik motor + 1 kanıt adaptörü) o alanı "hedefin
    gönderileri" diye okuyordu:

        agent_core/agents/target_psyche_profiler.py → LLM'e "Gönderi metni"
        agent_core/services/pillar_evidence_adapter.py → "corpus_basis:
            target_profile.bio + target_profile.posts"

    Yani bir arama motorunun 3 satırlık özeti, hedefin bizzat yazdığı metin
    gibi ölçülüyordu. Kanıt tipi (search_snippet) hiçbir yerde yazılı değildi.

Sözleşme (tek kaynak — bu modül):
    * ``posts``              → YALNIZCA platformdan kazınmış gönderi metni.
    * ``post_evidence_types``→ ``posts`` ile PARALEL liste; her öğenin kanıt tipi.
    * ``search_snippets``    → arama sonucu snippet'ları (kanıt tipi: search_snippet).
    * ``content_basis``      → corpus'un ne olduğunun TEK makine-okunur beyanı.

Tüketici kuralı:
    * "Hedefin kendi yazdığı metin" iddiası kurulan yerler (authenticity,
      human_behavior) YALNIZCA ``platform_post`` türünü kullanır; arama
      sonucu üçüncü taraf metnidir, hedefin beyanı DEĞİLDİR.
    * Genel muhakeme (tutku/zihin) yapan yerler (target_psyche_profiler)
      snippet'ı DA kullanır ama ETİKETİYLE: "arama sonucu" diye yazar.
    * Ölçüm motorları (frequency/gravity/void) yalnız ``posts`` okur; snippet
      koşusunda frekans iddiası ÜRETİLMEZ (dürüst boş).

Bu modul bir yetenek değildir; alan sözleşmesidir. Mevcut ``posts`` alanını
**silmez** — geriye dönük uyum korunur, yalnız tip etiketi KAYBOLMAZ.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from pydantic import BaseModel, ConfigDict

__all__ = [
    "EVIDENCE_PLATFORM_POST",
    "EVIDENCE_SEARCH_SNIPPET",
    "EVIDENCE_AGENT_REACH",
    "EVIDENCE_NONE",
    "CONTENT_BASIS_PLATFORM",
    "CONTENT_BASIS_SEARCH",
    "CONTENT_BASIS_MIXED",
    "CONTENT_BASIS_NONE",
    "PublicText",
    "content_basis",
    "extract_public_text",
    "render_corpus_block",
]

#: Kanıt tipleri (kanıt zincirine giren etiketlerle aynı dil).
EVIDENCE_PLATFORM_POST = "platform_post"
EVIDENCE_SEARCH_SNIPPET = "search_snippet"
EVIDENCE_AGENT_REACH = "agent_reach_text"
EVIDENCE_NONE = "none"

#: Corpus beyanı (target_profile.content_basis).
CONTENT_BASIS_PLATFORM = "platform_post"
CONTENT_BASIS_SEARCH = "search_snippet"
CONTENT_BASIS_MIXED = "mixed"
CONTENT_BASIS_NONE = "none"

#: Prompt'ta kullanıcıya gösterilen okunur etiketler.
_LABELS = {
    EVIDENCE_PLATFORM_POST: "gönderi",
    EVIDENCE_SEARCH_SNIPPET: "arama sonucu (hedefin gönderisi DEĞİLDİR)",
    EVIDENCE_AGENT_REACH: "doğrudan okuma (gönderi değil)",
}

#: Etiket sırası (deterministik).
_KIND_ORDER = (EVIDENCE_PLATFORM_POST, EVIDENCE_AGENT_REACH, EVIDENCE_SEARCH_SNIPPET)


class PublicText(BaseModel):
    """Corpus'taki TEK metin parçası + kanıt tipi."""

    text: str
    evidence_type: str = EVIDENCE_NONE
    source_url: str | None = None
    provider: str | None = None

    model_config = ConfigDict(extra="forbid")


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "caption", "content"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return ""


def _evidence_type(value: Any) -> str:
    """Serbest metin etiketini bilinen kanıt tipine indirger."""
    text = str(value or "").strip().lower()
    if text in _KIND_ORDER:
        return text
    if text in {"text", "image", "video", "reel", "carousel", "unknown"}:
        # Eski platform_registry etiketleri ("text" vb.) gerçek gönderidir.
        return EVIDENCE_PLATFORM_POST
    return EVIDENCE_NONE


def extract_public_text(
    target_profile: Any,
    *,
    kinds: Sequence[str] | None = None,
) -> list[PublicText]:
    """``target_profile`` içindeki metinleri kanıt tipiyle birlikte döndürür.

    ``kinds`` verilirse yalnız o tipler alınır (örn. yalnız ``platform_post``).
    Sıra: önce platform gönderileri, sonra agent-reach metni, sonra snippet'lar.
    """
    if not isinstance(target_profile, dict):
        return []
    wanted = set(kinds) if kinds else None

    items: list[PublicText] = []

    raw_posts = target_profile.get("posts")
    posts = raw_posts if isinstance(raw_posts, (list, tuple)) else []
    raw_types = target_profile.get("post_evidence_types")
    types = list(raw_types) if isinstance(raw_types, (list, tuple)) else []
    for index, post in enumerate(posts):
        text = _as_text(post)
        if not text:
            continue
        kind = _evidence_type(types[index]) if index < len(types) else EVIDENCE_PLATFORM_POST
        if kind == EVIDENCE_NONE:
            kind = EVIDENCE_PLATFORM_POST
        if wanted is not None and kind not in wanted:
            continue
        source_url = None
        provider = None
        if isinstance(post, dict):
            raw_url = post.get("source_url") or post.get("url")
            source_url = raw_url if isinstance(raw_url, str) and raw_url else None
            raw_provider = post.get("provider")
            provider = raw_provider if isinstance(raw_provider, str) and raw_provider else None
        items.append(
            PublicText(text=text, evidence_type=kind, source_url=source_url, provider=provider)
        )

    raw_snippets = target_profile.get("search_snippets")
    snippets = raw_snippets if isinstance(raw_snippets, (list, tuple)) else []
    for snippet in snippets:
        text = _as_text(snippet)
        if not text:
            continue
        if wanted is not None and EVIDENCE_SEARCH_SNIPPET not in wanted:
            continue
        source_url = None
        provider = None
        if isinstance(snippet, dict):
            raw_url = snippet.get("source_url") or snippet.get("url")
            source_url = raw_url if isinstance(raw_url, str) and raw_url else None
            raw_provider = snippet.get("provider")
            provider = raw_provider if isinstance(raw_provider, str) and raw_provider else None
        items.append(
            PublicText(
                text=text,
                evidence_type=EVIDENCE_SEARCH_SNIPPET,
                source_url=source_url,
                provider=provider,
            )
        )

    def sort_key(item: PublicText) -> int:
        try:
            return _KIND_ORDER.index(item.evidence_type)
        except ValueError:
            return len(_KIND_ORDER)

    items.sort(key=sort_key)
    return items


def content_basis(target_profile: Any) -> str:
    """Corpus'un ne olduğunun TEK makine-okunur beyanı.

    ``platform_post`` | ``search_snippet`` | ``mixed`` | ``none``
    """
    if not isinstance(target_profile, dict):
        return CONTENT_BASIS_NONE
    items = extract_public_text(target_profile)
    kinds = {item.evidence_type for item in items}
    if not kinds:
        return CONTENT_BASIS_NONE
    if kinds == {EVIDENCE_SEARCH_SNIPPET}:
        return CONTENT_BASIS_SEARCH
    if EVIDENCE_SEARCH_SNIPPET in kinds:
        return CONTENT_BASIS_MIXED
    return CONTENT_BASIS_PLATFORM


def render_corpus_block(
    items: Iterable[PublicText],
    *,
    limit: int = 10,
    empty_text: str = "Metin bulunamadı.",
) -> str:
    """Etiketli corpus metni — prompt'a girmeden önce tip KAYBOLMAZ."""
    rendered: list[str] = []
    for item in list(items)[: max(0, int(limit))]:
        label = _LABELS.get(item.evidence_type, item.evidence_type)
        line = f"- [{label}] {item.text}"
        if item.source_url:
            line += f" (kaynak: {item.source_url})"
        rendered.append(line)
    if not rendered:
        return empty_text
    return "\n".join(rendered)
