"""FAZ D · D1 — yetenek defteri → MCP araçları (tek kaynak, uydurma yok).

Kural [009]: "bu yetenek var mı?" sorusunun TEK cevabı ``CapabilityRegistry``'dir.
Bu modül ikinci bir envanter TUTMAZ: araç listesi her istekte defterden türetilir.
Deftere yeni bir yetenek girdiğinde MCP araç listesi kendiliğinden büyür; kimse
ikinci bir liste güncellemek zorunda değildir (bayat liste = sessiz yalan).

İki yön vardır ve ikisi de aynı sözleşmeden geçer:
    * ``build_tools``  : Capability → MCP aracı (ad, açıklama, JSON Schema).
    * ``resolve_tool`` : MCP aracı → Capability (ad çakışması fail-closed).

Araç adı kuralı: MCP ad sözdizimi ``^[a-zA-Z0-9_-]{1,128}$``'dir; yetenek
kimlikleri noktalı küçük harftir (``sensor.identity.maigret``). Dönüşüm noktayı
alt çizgiye çevirir. Bu dönüşüm BİREBİR DEĞİLDİR (``a.b_c`` ile ``a_b.c`` aynı
ada düşer) — bu yüzden kurulum anında çakışma aranır ve bulunursa gürültülü
hata verilir; sessizce bir yeteneğin üstüne yazmak yasaktır.

Girdi şeması: yetenek kendi şemasını ``mcp_input_schema`` ile beyan eder
(tek kaynak yine yeteneğin kendisidir). Beyan yoksa varsayılan şema
``subject``'tir ve bu uydurma değildir: ``CapabilityContext.subject``
sözleşmenin parçasıdır.
"""

from __future__ import annotations

import re
from typing import Any

from agent_core.capabilities.base import Capability, CapabilityContext, CapabilityKind
from agent_core.capabilities.registry import CapabilityRegistry

__all__ = [
    "TOOL_NAME_RE",
    "MCP_TOOL_PREFIX",
    "tool_name_for",
    "build_tool_index",
    "build_tools",
    "default_input_schema",
    "input_schema_for",
    "arguments_to_context",
]

TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

#: Yetenek araçları ``pineal_`` önekini TAŞIMAZ; yalnız sunucunun kendi
#: araçları (durum) bu öneki kullanır — böylece "bu Pineal'in kendisi mi,
#: yoksa dışa açılan bir yetenek mi" sorusu addan okunur.
MCP_TOOL_PREFIX = "pineal_"

_SUBJECT_DESCRIPTION = (
    "Hedef: kullanıcı adı, e-posta, URL ya da yeteneğin beklediği metin "
    "(CapabilityContext.subject sözleşmesi)."
)

#: Yetenek türü → MCP davranış ipuçları (spec: annotations). İpuçları
#: yeteneğin GERÇEK davranışından türetilir, pazarlama metni değildir:
#: sensör/çıkarıcı dış dünyayı okur; ses/rapor yerel dosya ÜRETİR.
_ANNOTATIONS: dict[CapabilityKind, dict[str, bool]] = {
    CapabilityKind.SENSOR: {"readOnlyHint": True, "openWorldHint": True},
    CapabilityKind.EXTRACTOR: {"readOnlyHint": True, "openWorldHint": True},
    CapabilityKind.ANALYZER: {"readOnlyHint": True, "openWorldHint": False},
    CapabilityKind.VERIFIER: {"readOnlyHint": True, "openWorldHint": True},
    CapabilityKind.MEMORY: {"readOnlyHint": True, "openWorldHint": False},
    CapabilityKind.RENDERER: {"readOnlyHint": False, "openWorldHint": False},
    CapabilityKind.TOOL: {"readOnlyHint": False, "openWorldHint": True},
}


def tool_name_for(cap_id: str) -> str:
    """Yetenek kimliğini MCP araç adına çevirir (deterministik)."""
    return cap_id.replace(".", "_")


def default_input_schema() -> dict[str, Any]:
    """Beyan edilmemiş yetenekler için sözleşme şeması: yalnız ``subject``."""
    return {
        "type": "object",
        "properties": {"subject": {"type": "string", "description": _SUBJECT_DESCRIPTION}},
        "required": ["subject"],
        "additionalProperties": False,
    }


def input_schema_for(cap: Capability) -> dict[str, Any]:
    """Yeteneğin girdi şeması: kendi beyanı ya da sözleşme varsayılanı.

    Beyan edilen şema ``subject`` alanını dışarıda bırakamaz; bırakırsa
    eklenir (``CapabilityContext.subject`` her çağrıda mevcuttur ve şemada
    görünmemesi istemciye yalan söylerdi).
    """
    declared = getattr(cap, "mcp_input_schema", None)
    if not isinstance(declared, dict) or not declared:
        return default_input_schema()
    schema = dict(declared)
    properties = dict(schema.get("properties") or {})
    if "subject" not in properties:
        properties = {
            "subject": {"type": "string", "description": _SUBJECT_DESCRIPTION},
            **properties,
        }
    schema["properties"] = properties
    schema.setdefault("type", "object")
    schema.setdefault("required", [])
    if "additionalProperties" not in schema:
        schema["additionalProperties"] = False
    return schema


def build_tool_index(registry: CapabilityRegistry) -> dict[str, str]:
    """{araç adı → yetenek kimliği}. Çakışma varsa gürültülü hata (fail-closed)."""
    index: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for cap_id in registry.ids():
        name = tool_name_for(cap_id)
        if not TOOL_NAME_RE.match(name):  # savunma: defter kimliği değişirse görünür
            raise ValueError(
                f"MCP araç adı sözdizime uymuyor: {name!r} (kaynak: {cap_id!r})"
            )
        if name in index:
            collisions.setdefault(name, [index[name]]).append(cap_id)
            continue
        index[name] = cap_id
    if collisions:
        raise ValueError(
            "MCP araç adı çakışması — iki yetenek aynı ada düşüyor: "
            + "; ".join(f"{n} ← {ids}" for n, ids in sorted(collisions.items()))
        )
    return index


def build_tools(registry: CapabilityRegistry) -> list[dict[str, Any]]:
    """MCP ``tools/list`` yanıtı: yetenek başına bir araç (deterministik sıra).

    Sıra kimliğe göre sabittir: spec "aynı araç kümesi için aynı sıralama"
    ister (istemci önbelleği + prompt önbelleği). Hiçbir alan uydurulmaz:
    açıklama yeteneğin kendi ``description`` alanıdır, kapılar kendi
    ``gates`` kümesidir.
    """
    tools: list[dict[str, Any]] = []
    for cap_id in registry.ids():  # registry.ids() sıralıdır (deterministik)
        cap = registry.get(cap_id)
        gates = sorted(getattr(cap, "gates", frozenset()))
        description = (getattr(cap, "description", "") or "").strip() or cap_id
        if gates:
            description = (
                f"{description}\n\nKapılar: {', '.join(gates)}. "
                "Kasa kilitliyken ya da kapı kapalıyken yetenek KOŞMAZ "
                "(fail-closed); çağrı dürüst bir sebeple reddedilir."
            )
        kind = getattr(cap, "kind", CapabilityKind.SENSOR)
        tools.append(
            {
                "name": tool_name_for(cap_id),
                "title": cap_id,
                "description": description,
                "inputSchema": input_schema_for(cap),
                "annotations": dict(_ANNOTATIONS.get(kind, {})),
            }
        )
    return tools


def arguments_to_context(
    arguments: dict[str, Any] | None,
    *,
    task_id: str = "",
    timeout_seconds: float | None = None,
) -> CapabilityContext:
    """MCP ``arguments`` → ``CapabilityContext`` (tek eşleme kuralı).

    Kural: ``subject`` çağrı bağlamının subject'idir, kalan her argüman
    ``params`` içine girer. Yetenekler zaten ``ctx.subject or ctx.params[...]``
    desenini kullandığı için bu eşleme mevcut adaptörlerle birebir uyumludur.
    """
    args = dict(arguments or {})
    subject = args.pop("subject", "")
    if not isinstance(subject, str):
        subject = str(subject)
    params = {key: value for key, value in args.items() if key != "_meta"}
    return CapabilityContext(
        subject=subject.strip(),
        task_id=task_id,
        params=params,
        timeout_seconds=timeout_seconds,
    )
