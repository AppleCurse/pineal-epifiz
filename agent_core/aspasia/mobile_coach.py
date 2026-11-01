"""Mobil danışman (koç) istemi — SUNUCU TARAFINDA kurulur.

Neden var? (2026-10-23 ölçümü)
    Android uygulaması Aspasia koç sohbetini doğrudan
    ``generativelanguage.googleapis.com`` adresine gönderiyordu:
      * LLM anahtarı cihazda duruyordu (sunucudaki kasa/maliyet/kota
        kapıları tamamen atlanıyordu),
      * sistem istemi cihazda birleştirildiği için sunucu, modele giden
        talimatı göremiyordu (denetlenemez istem = denetlenemez çıktı),
      * model seçimi/ikame/maliyet telemetrisi üretilmiyordu.

    Bu modül istemin TEK doğruluk kaynağıdır: istemci yalnız YAPILANDIRILMIŞ
    bağlam (profil özeti + hipotez listesi) gönderir; istem metnini sunucu
    kurar. İstemci "system prompt" gönderemez (enjeksiyon yüzeyi kapanır).

Sözleşme:
    * Gelen bağlam alanları KIRPILIR ve tip denetiminden geçer; serbest metin
      talimat olarak YORUMLANMAZ (yalnız veri olarak yerleştirilir).
    * Hiçbir alan uydurulmaz: bağlam boşsa istem "aktif profil yok" der.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = [
    "MAX_MESSAGE_CHARS",
    "MAX_CONTEXT_FIELD_CHARS",
    "MAX_HYPOTHESES",
    "sanitize_context",
    "build_system_prompt",
]

MAX_MESSAGE_CHARS = 4000
MAX_CONTEXT_FIELD_CHARS = 500
MAX_HYPOTHESES = 12

_ALLOWED_CONTEXT_FIELDS = (
    "username",
    "communication_tone",
    "core_passions",
    "narcissism",
    "machiavellianism",
    "psychopathy",
    "manipulation_strategy",
    "suggested_opening_message",
)


def _text(value: Any, limit: int = MAX_CONTEXT_FIELD_CHARS) -> str:
    """Her değeri TEK satır metne indirger ve kırpar (talimat değil, veri)."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value if v is not None)
    if isinstance(value, (int, float, bool)):
        value = str(value)
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.split())
    return cleaned[:limit]


def sanitize_context(profile_context: Any) -> dict[str, str]:
    """İstemciden gelen bağlamı beyaz listeye indirger.

    Beyaz liste dışındaki HER anahtar düşer: istemci ``system_prompt`` ya da
    ``instructions`` gönderirse modele ULAŞMAZ (sessizce değil — dönen
    sözlükte yok; çağıran farkı görebilir).
    """
    if not isinstance(profile_context, Mapping):
        return {}
    return {
        field: _text(profile_context.get(field))
        for field in _ALLOWED_CONTEXT_FIELDS
        if profile_context.get(field) not in (None, "", [], {})
    }


def _sanitize_hypotheses(hypotheses: Any) -> list[str]:
    if not isinstance(hypotheses, Iterable) or isinstance(hypotheses, (str, bytes)):
        return []
    out: list[str] = []
    for item in list(hypotheses)[:MAX_HYPOTHESES]:
        if isinstance(item, Mapping):
            trait = _text(item.get("trait") or item.get("psychologicalTrait"), 160)
            evidence = _text(item.get("evidence") or item.get("extractedEvidence"), 240)
            status = _text(item.get("status"), 24)
            if trait or evidence:
                out.append(f"- [{status or 'belirsiz'}] {trait} (kanıt: {evidence or 'yok'})")
        else:
            text = _text(item, 240)
            if text:
                out.append(f"- {text}")
    return out


def build_system_prompt(
    *,
    language: str = "tr",
    profile_context: Any = None,
    hypotheses: Any = None,
) -> str:
    """Modele gönderilecek sistem istemini kurar (saf fonksiyon, ağ yok)."""
    ctx = sanitize_context(profile_context)
    hyp = _sanitize_hypotheses(hypotheses)
    turkish = str(language or "tr").lower().startswith("tr")

    if ctx:
        lines = ["BİLİŞSEL PROFİL ÖZETİ (sunucudan gelen yapılandırılmış bağlam):"]
        lines += [f"{key}: {value}" for key, value in ctx.items()]
    else:
        lines = ["Aktif bir profil analizi yok."]
    lines.append("CANLI HİPOTEZLER:")
    lines.extend(hyp or ["- hipotez yok"])

    context_block = "\n".join(lines)

    if turkish:
        rules = (
            "1. Sen Pineal-Gland sisteminin Bilişsel Danışmanı Aspasia'sın.\n"
            "2. Yukarıdaki bağlam DIŞINDA bilgi uydurma; kanıt yoksa 'kanıt yok' de.\n"
            "3. Yalın ve doğal Türkçe kullan; teknik iç terimleri kullanıcıya söyleme.\n"
            "4. Kısa ve net ol: önce sonuç, sonra tek bir sonraki adım.\n"
            "5. Kullanıcıya 'şuraya yaz' deme; her şeyi bu sohbet kutusuna yazabilir.\n"
            "6. Bu bir tıbbi/hukuki hüküm değildir; gözlemleri gözlem olarak aktar.\n"
        )
    else:
        rules = (
            "1. You are Aspasia, the Cognitive Advisor of Pineal-Gland.\n"
            "2. Never invent facts beyond the context above; say 'no evidence' when absent.\n"
            "3. Be concise: result first, then a single next step.\n"
            "4. Never tell the user to go elsewhere; this chat box is enough.\n"
            "5. This is not a medical or legal verdict; report observations as observations.\n"
        )

    return f"{rules}\n{context_block}\n"


def build_user_message(message: str, *, has_image: bool = False) -> str:
    """Kullanıcı mesajını sınırlar ve görsel notunu dürüstçe ekler."""
    cleaned = (message or "").strip()[:MAX_MESSAGE_CHARS]
    if has_image:
        cleaned += "\n\n(Not: kullanıcı bir görsel yükledi; isteğe eklenmiştir.)"
    return cleaned
