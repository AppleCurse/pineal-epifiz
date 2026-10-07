"""FAZ D · D1 — CapabilityResult → MCP sonucu (dürüst çeviri).

Üç kural:

1. **Kanıtsız iddia yok.** Yetenek kanıt üretmediyse sonuç ``isError: true``
   döner ve sebep MAKİNE-OKUNUR taşınır (``unavailable_reason`` /
   ``denied_by`` / ``error``). "0 kanıt + hata yok" diye bir sonuç yoktur.
2. **Sürüm dürüstlüğü.** ``structuredContent`` 2025-06-18'de geldi;
   ``resultType`` 2026-07-28'nin alanıdır. Eski istemciye yeni alan
   gönderilmez (istemci sözleşmesine uydurma alan eklenmez).
3. **Kırpma gizlenmez.** Uzun kanıt kırpılırsa ``truncated`` olarak işaretlenir.
"""

from __future__ import annotations

from typing import Any

from agent_core.capabilities.base import CapabilityResult

__all__ = [
    "STRUCTURED_CONTENT_VERSIONS",
    "RESULT_TYPE_VERSION",
    "supports_structured_content",
    "max_content_chars",
    "render_result",
]

#: ``structuredContent`` bu revizyonlarda geçerlidir (2025-06-18'de eklendi).
STRUCTURED_CONTENT_VERSIONS = frozenset({"2026-07-28", "2025-11-25", "2025-06-18"})

#: ``resultType`` alanı bu revizyonun sözleşmesidir.
RESULT_TYPE_VERSION = "2026-07-28"

#: Tek metin bloğunun tavanı: kanıt şişip istemci bağlamını yakmasın.
_MAX_TEXT_CHARS = 4000
_MAX_EVIDENCE_ITEMS = 50


def supports_structured_content(protocol_version: str) -> bool:
    return protocol_version in STRUCTURED_CONTENT_VERSIONS


def max_content_chars() -> int:
    return _MAX_TEXT_CHARS


def _clip(text: str, limit: int = _MAX_TEXT_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _evidence_line(item: Any) -> str:
    parts = [f"[{item.evidence_id}]", f"({item.epistemic_type} · {item.source_engine}"]
    if item.confidence is not None:
        parts.append(f"· güven {item.confidence:.2f}")
    parts.append(")")
    line = " ".join(parts) + f" {item.content}"
    if getattr(item, "provenance_refs", None):
        line += " · kaynak: " + ", ".join(str(ref) for ref in item.provenance_refs[:5])
    return line


def _payload_of(result: CapabilityResult) -> Any:
    payload = result.payload
    for attr in ("model_dump", "to_dict", "dict"):
        method = getattr(payload, attr, None)
        if callable(method):
            try:
                return method()
            except Exception:  # pragma: no cover - savunma: payload serileşmezse ham kalır
                return None
    return payload


def render_result(result: CapabilityResult, *, protocol_version: str) -> dict[str, Any]:
    """Yeteneğin sonucunu MCP ``tools/call`` sonucuna çevirir."""
    structured: dict[str, Any] = {
        "capability_id": result.capability_id,
        "available": bool(result.available),
        "ok": bool(result.ok),
        "unavailable_reason": result.unavailable_reason,
        "denied_by": result.denied_by,
        "error": result.error,
        "evidence_count": len(result.items),
        "evidence_ids": [item.evidence_id for item in result.items],
        "notes": dict(result.notes or {}),
        "duration_ms": result.duration_ms,
        "cost_usd": result.cost_usd,
    }
    payload = _payload_of(result)
    if payload is not None:
        structured["payload"] = payload

    lines: list[str] = []
    if result.items:
        lines.append(f"{result.capability_id}: {len(result.items)} kanıt")
        for item in list(result.items)[:_MAX_EVIDENCE_ITEMS]:
            lines.append(_evidence_line(item))
        if len(result.items) > _MAX_EVIDENCE_ITEMS:
            lines.append(
                f"… {len(result.items) - _MAX_EVIDENCE_ITEMS} kanıt daha var "
                "(kırpıldı; tam liste evidence_id ile ayrıca istenebilir)"
            )
    if not result.available or result.error:
        reason = result.unavailable_reason or result.error or "bilinmeyen"
        lines.append(f"{result.capability_id}: KOŞMADI — {reason}")
        if result.denied_by:
            lines.append(f"reddeden kapı: {result.denied_by}")
    if result.notes:
        note_bits = [f"{key}={value}" for key, value in sorted(result.notes.items())]
        lines.append("notlar: " + " · ".join(note_bits))

    text, truncated = _clip("\n".join(lines) if lines else f"{result.capability_id}: sonuç yok")
    if truncated:
        structured["truncated"] = True

    rendered: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": not result.ok,
    }
    if supports_structured_content(protocol_version):
        rendered["structuredContent"] = structured
    if protocol_version == RESULT_TYPE_VERSION:
        rendered["resultType"] = "complete"
    return rendered
