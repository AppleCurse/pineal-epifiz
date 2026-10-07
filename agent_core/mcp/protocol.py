"""FAZ D · D1 — MCP (Model Context Protocol) tel katmanı: JSON-RPC 2.0 + sürüm.

Neden ayrı dosya: protokol kuralları (mesaj doğrulama, sürüm anlaşması, hata
kodları) I/O'dan bağımsız saf fonksiyonlardır. Bu sayede tel katmanı
süreç/stdio olmadan test edilir; sunucu (``server.py``) yalnızca taşıma ve
sevkiyat yapar.

Sürüm gerçeği (ölçüldü, 2026-10-07):
    * Güncel sürüm **2026-07-28**'dir ve protokol ARTIK STATELESS'tir:
      ``initialize`` el sıkışması kaldırıldı; sürüm ve istemci yetenekleri her
      isteğin ``_meta`` alanında taşınır, keşif ``server/discover`` ile yapılır.
    * Eski istemciler (2025-11-25 ve öncesi) hâlâ ``initialize`` el sıkışmasını
      konuşur. Bu sunucu İKİSİNİ birlikte destekler: el sıkışması gelirse
      yanıtlanır, ``_meta`` sürümü gelirse ona göre davranılır. Tek bir
      istemciyi dışarıda bırakmak "standart protokol" iddiasını bozardı.

Dürüstlük kuralı: bilinmeyen/desteklenmeyen sürüm sessizce en yenisi sanılmaz —
``server/discover`` desteklenen sürümleri SAYAR, anlaşmazlık ise açık hata
döner (``UNSUPPORTED_PROTOCOL_VERSION`` + desteklenen liste).
"""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "PROTOCOL_VERSION",
    "LEGACY_PROTOCOL_VERSIONS",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "META_VERSION_KEY",
    "META_CLIENT_INFO_KEY",
    "META_SERVER_INFO_KEY",
    "JSONRPC_VERSION",
    "MAX_LINE_BYTES",
    "ErrorCode",
    "RPCError",
    "notification",
    "error_response",
    "success_response",
    "parse_message",
    "request_meta",
    "request_protocol_version",
    "negotiate_version",
    "is_supported_version",
    "unsupported_version_error",
    "is_notification",
]

#: Sunucunun konuştuğu en güncel sürüm (stateless çekirdek).
PROTOCOL_VERSION = "2026-07-28"

#: Geriye dönük uyumluluk: el sıkışmalı (session-based) revizyonlar.
LEGACY_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)

SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (PROTOCOL_VERSION, *LEGACY_PROTOCOL_VERSIONS)

JSONRPC_VERSION = "2.0"

#: stdio taşıması satır-başına JSON'dur (NDJSON). Tek satır için tavan: bozuk
#: ya da kötü niyetli bir istemci belleği şişiremez (aşarsa dürüst hata).
MAX_LINE_BYTES = 8 * 1024 * 1024

#: 2026-07-28 ``_meta`` anahtarları (istek başına sürüm + kimlik).
META_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"


class ErrorCode:
    """JSON-RPC 2.0 çekirdek kodları + MCP'ye özgü kodlar."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    #: Legacy (el sıkışmalı) oturumda initialize'den önce gelen istek.
    SERVER_NOT_INITIALIZED = -32002
    #: 2026-07-28: sürüm anlaşmazlığı (desteklenen liste ``data`` içinde döner).
    UNSUPPORTED_PROTOCOL_VERSION = -32022


class RPCError(Exception):
    """Taşıma katmanında yakalanan, istemciye JSON-RPC hatası olarak dönen hata."""

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_response(self, request_id: Any) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bildirim zarfı (id YOK — yanıt beklenmez)."""
    message: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
    if params:
        message["params"] = params
    return message


def success_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(
    request_id: Any, code: int, message: str, data: Any | None = None
) -> dict[str, Any]:
    return RPCError(code, message, data).to_response(request_id)


def parse_message(line: str) -> dict[str, Any]:
    """Tek satırı JSON-RPC 2.0 zarfına çözer; bozuksa ``RPCError``.

    Doğrulanan şey zarfın kendisidir: ``jsonrpc == "2.0"`` ve ``method`` bir
    metin. ``id`` yokluğu bildirim demektir (geçerli).
    """
    raw = line or ""
    # Boyut denetimi HAM satıra uygulanır: strip() sonrası ölçmek, dolgu
    # karakterlerle tavanı atlatmaya izin verirdi (test bunu yakaladı).
    if len(raw.encode("utf-8", "replace")) > MAX_LINE_BYTES:
        raise RPCError(
            ErrorCode.INVALID_REQUEST,
            f"satır çok büyük (> {MAX_LINE_BYTES} bayt)",
        )
    text = raw.strip()
    if not text:
        raise RPCError(ErrorCode.INVALID_REQUEST, "boş satır")
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise RPCError(ErrorCode.PARSE_ERROR, f"JSON çözülemedi: {exc}") from exc
    if not isinstance(payload, dict):
        raise RPCError(ErrorCode.INVALID_REQUEST, "mesaj JSON nesnesi olmalı")
    if payload.get("jsonrpc") != JSONRPC_VERSION:
        raise RPCError(ErrorCode.INVALID_REQUEST, "jsonrpc alanı '2.0' olmalı")
    if not isinstance(payload.get("method"), str) or not payload["method"]:
        raise RPCError(ErrorCode.INVALID_REQUEST, "method alanı metin olmalı")
    params = payload.get("params")
    if params is not None and not isinstance(params, dict):
        raise RPCError(ErrorCode.INVALID_PARAMS, "params nesne olmalı")
    return payload


def request_meta(message: dict[str, Any]) -> dict[str, Any]:
    """İsteğin ``_meta`` alanı (yoksa boş sözlük — uydurma YOK)."""
    params = message.get("params")
    if isinstance(params, dict):
        meta = params.get("_meta")
        if isinstance(meta, dict):
            return meta
    return {}


def request_protocol_version(message: dict[str, Any]) -> str | None:
    """İsteğin beyan ettiği sürüm: ``_meta`` ya da legacy ``protocolVersion``.

    İkisi de yoksa ``None`` döner: çağıran bunu "beyan yok" olarak okur
    (stateless istemci sürümü her istekte taşımalıdır; eksikse en yenisi
    varsayılmaz, oturum sürümü/``None`` kullanılır).
    """
    meta_value = request_meta(message).get(META_VERSION_KEY)
    if isinstance(meta_value, str) and meta_value.strip():
        return meta_value.strip()
    params = message.get("params")
    if isinstance(params, dict):
        declared = params.get("protocolVersion")
        if isinstance(declared, str) and declared.strip():
            return declared.strip()
    return None


def negotiate_version(requested: str | None) -> str:
    """(sunucunun yanıt vereceği sürüm, uyumlu mu) ikilisinin sürüm tarafı.

    Kural: istenen sürüm destekleniyorsa AYNEN onaylanır; desteklenmiyorsa
    sunucu kendi en güncel sürümünü döndürür (MCP sürüm anlaşması sözleşmesi:
    "server MUST respond with a version it supports"). İstemci beğenmezse
    bağlantıyı kapatır — bu sunucu sessizce eski sürüm gibi davranmaz.
    """
    if requested and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return PROTOCOL_VERSION


def is_supported_version(version: str | None) -> bool:
    return bool(version) and version in SUPPORTED_PROTOCOL_VERSIONS


def is_notification(message: dict[str, Any]) -> bool:
    return "id" not in message


def unsupported_version_error(requested: str | None) -> RPCError:
    """Sürüm anlaşmazlığı: desteklenen liste makine-okunur döner (gizlenmez)."""
    return RPCError(
        ErrorCode.UNSUPPORTED_PROTOCOL_VERSION,
        f"desteklenmeyen protokol sürümü: {requested!r}",
        data={
            "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "requestedVersion": requested,
        },
    )
