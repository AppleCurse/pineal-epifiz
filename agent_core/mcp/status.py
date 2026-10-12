"""FAZ D · D1 — MCP sunucusunun KENDİ durum aracı (``pineal_status``).

Neden gerekli: dışarıdaki bir istemci (Claude vb.) "hangi yetenekler koşabilir,
hangileri neden koşmuyor?" sorusunun cevabını yalnızca çağrı deneyerek
öğrenemez. Bu araç o soruyu TEK gerçek kaynaktan yanıtlar: ``CapabilityRegistry``
+ ``PolicyKernel``. Hiçbir alan uydurulmaz; kullanılamayan yetenek için sebep
makine-okunur döner (``reason`` + ``policy_reason``).
"""

from __future__ import annotations

from typing import Any

from agent_core.capabilities.base import CapabilityKind
from agent_core.capabilities.policy import PolicyKernel, PolicyState
from agent_core.capabilities.registry import CapabilityRegistry

__all__ = ["STATUS_TOOL_NAME", "status_tool_definition", "build_status_report"]

STATUS_TOOL_NAME = "pineal_status"


def status_tool_definition() -> dict[str, Any]:
    """Sunucunun kendi durum aracının MCP tanımı (girdisiz)."""
    return {
        "name": STATUS_TOOL_NAME,
        "title": "Pineal durumu",
        "description": (
            "Pineal'in yetenek envanterini ve her yeteneğin ŞU AN koşup "
            "koşamayacağını raporlar (kasa mandalı, kapı bayrakları, hız sınırı). "
            "Kanıt üretmez; yalnızca dürüst durum tablosu döner. Bir araç "
            "çağrısı reddedildiğinde sebebi buradan okunur."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    }


def _kind_label(row: dict[str, Any]) -> str:
    try:
        return CapabilityKind(row.get("kind", "")).value
    except ValueError:
        return str(row.get("kind") or "?")


def build_status_report(
    registry: CapabilityRegistry,
    *,
    state: PolicyState,
    kernel: PolicyKernel | None = None,
    snapshot: dict[str, Any] | None = None,
    server: dict[str, Any] | None = None,
    rate_limit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """(text, structured) ikilisini üretir — ikisi aynı gerçeği taşır."""
    kernel = kernel or PolicyKernel()
    rows = registry.status(state, kernel=kernel)

    lines: list[str] = []
    if server:
        lines.append(
            f"{server.get('name', 'pineal')} v{server.get('version', '?')} · "
            f"taşıma stdio · protokol {server.get('protocol_version', '?')}"
        )
    lines.append(f"yetenek sayısı: {len(rows)}")

    if snapshot:
        api_url = snapshot.get("api_url") or "(tanımsız)"
        if snapshot.get("vault_locked"):
            reason = snapshot.get("vault_reason") or "kasa kilitli"
            lines.append(f"KASA: KİLİTLİ ({reason}) · API: {api_url}")
        else:
            lines.append(f"KASA: AÇIK · API: {api_url}")
    if rate_limit:
        lines.append(
            f"hız sınırı: {rate_limit.get('limit')} çağrı / "
            f"{rate_limit.get('window_seconds')} sn (araç başına)"
        )

    lines.append("")
    for row in rows:
        gate_state = (
            "izinli"
            if row.get("policy_allowed")
            else f"ret:{row.get('policy_reason') or 'bilinmiyor'}"
        )
        availability = (
            "hazır" if row.get("available") else f"hazır değil:{row.get('reason')}"
        )
        lines.append(
            f"- {row['id']} [{_kind_label(row)}] · {availability} · {gate_state}"
            + (f" · kapılar: {', '.join(row['gates'])}" if row.get("gates") else "")
        )

    structured = {
        "server": dict(server or {}),
        "vault": dict(snapshot or {}),
        "rate_limit": dict(rate_limit or {}),
        "capability_count": len(rows),
        "capabilities": rows,
    }
    return {"text": "\n".join(lines), "structured": structured}
