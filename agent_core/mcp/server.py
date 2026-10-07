"""FAZ D · D1 — MCP sunucusu: Pineal'in yetenekleri standart kapıdan dışarıda.

Ne yapar: kayıtlı her yeteneği (``CapabilityRegistry`` — tek kaynak) MCP aracı
olarak yayınlar ve çağrıları ``CapabilityRunner`` üzerinden koşturur. Yani
dışarıdan gelen bir çağrı, içerideki bir çağrıyla AYNI mandallardan geçer:
çocuk kilidi → politika kapıları (kasa · bütçe · hız · ENABLE_*) →
kullanılabilirlik → koşu. Ayrı bir "dış yol" yoktur; çünkü ayrı yol = ayrı
gerçek olurdu.

Protokol gerçeği (2026-10-07): güncel MCP sürümü **2026-07-28**'dir ve
STATELESS'tir (``initialize`` kaldırıldı, sürüm her isteğin ``_meta``'sında).
Eski istemciler el sıkışma konuşur. Bu sunucu ikisini birlikte destekler:

    * ``initialize`` + ``notifications/initialized`` → el sıkışmalı oturum
    * ``_meta['io.modelcontextprotocol/protocolVersion']`` → stateless istek
    * ``server/discover`` → desteklenen sürümler + yetenekler (keşif)

Yöntemler: ``tools/list`` · ``tools/call`` · ``ping`` · ``logging/setLevel`` ·
``server/discover``. Kaynak/istem (resources/prompts) ilan EDİLMEZ; ilan
edilmeyen bir ilkel için dürüst ``METHOD_NOT_FOUND`` döner (kanıt yoksa
iddia yok).

Taşıma: stdio, satır başına JSON (NDJSON). stdout YALNIZCA protokol
mesajlarına aittir; günlükler stderr'e gider — tek bir ``print`` bile
protokolü bozar (bu yüzden dosyada ``print`` yoktur).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from agent_core.capabilities.base import CapabilityResult
from agent_core.capabilities.policy import PolicyKernel, PolicyState
from agent_core.capabilities.registry import CapabilityRegistry, bootstrap
from agent_core.capabilities.runner import CapabilityRunner
from agent_core.mcp import protocol as p
from agent_core.mcp.results import render_result, supports_structured_content
from agent_core.mcp.state_bridge import (
    SlidingWindowLimiter,
    limiter_from_env,
    minor_case_for,
    policy_state_for_call,
    vault_state,
)
from agent_core.mcp.status import STATUS_TOOL_NAME, build_status_report, status_tool_definition
from agent_core.mcp.tools import (
    arguments_to_context,
    build_tool_index,
    build_tools,
)

logger = logging.getLogger(__name__)

__all__ = ["MCPServer", "SERVER_NAME", "server_version", "stdio_main"]

SERVER_NAME = "pineal-epifiz"

#: Sunucunun kendi araçları için önek (yetenek araçlarıyla karışmaz).
_SERVER_TOOLS = frozenset({STATUS_TOOL_NAME})


def server_version() -> str:
    """Sürüm tek kaynaktan: depo kökündeki ``VERSION`` dosyası."""
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return text or "unknown"


def _capabilities_declaration() -> dict[str, Any]:
    """Yalnız GERÇEKTEN desteklenen ilkeller ilan edilir."""
    return {"tools": {"listChanged": False}}


class MCPServer:
    """Durumsuz MCP sevkiyatçısı: mesaj alır, yanıt (veya None) döndürür.

    Ağ/stdio bilmez: ``handle`` saf bir fonksiyondur. Taşıma ``stdio_main``
    içindedir; böylece protokol davranışı süreç açmadan test edilir.
    """

    def __init__(
        self,
        *,
        registry: CapabilityRegistry | None = None,
        runner: CapabilityRunner | None = None,
        kernel: PolicyKernel | None = None,
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        self.registry = registry if registry is not None else bootstrap()
        self.kernel = kernel if kernel is not None else PolicyKernel()
        self.runner = runner if runner is not None else CapabilityRunner(registry=self.registry)
        self.limiter = limiter if limiter is not None else limiter_from_env()
        self.session_version: str | None = None
        self.initialized = False

    # --- yardımcılar ------------------------------------------------------
    # DİKKAT: ikinci bir env kaynağı YARATILMAZ. Sunucu da adaptörler de
    # süreç ortamını (os.environ) okur; enjekte edilebilir bir env sözlüğü
    # "sunucu açık sanıyor, adaptör kapalı" sapması üretiyordu (test yakaladı).
    def _env_get(self, name: str) -> str:
        return (os.environ.get(name) or "").strip()

    def _protocol_for(self, message: dict[str, Any]) -> str:
        """İsteğe uygulanacak sürüm: ``_meta`` > oturum > sunucu en yenisi."""
        declared = p.request_protocol_version(message)
        if declared:
            if not p.is_supported_version(declared):
                raise p.unsupported_version_error(declared)
            return declared
        return self.session_version or p.PROTOCOL_VERSION

    async def _policy_state(self, *, subject: str = "") -> tuple[PolicyState, dict[str, Any]]:
        """Kasa (API'den) + hız (yerel sınır) → politika durumu + dürüst özet."""
        locked, reason = await asyncio.to_thread(vault_state)
        snapshot = {
            "api_url": (self._env_get("PINEAL_API_URL") or "http://127.0.0.1:8000"),
            "vault_locked": locked,
            "vault_reason": reason or None,
            "client_id": self._env_get("PINEAL_MCP_CLIENT_ID") or "default",
        }
        state = policy_state_for_call(
            vault_locked=locked,
            # Sunucunun kendi giriş sınırı bu çağrı için kararını VERDİ; 'rate'
            # kapısı bildiren yetenekler için durum bu verdict'tir.
            rate_ok=True,
            minor_case=minor_case_for(subject),
        )
        return state, snapshot

    def _rate_check(self, tool_name: str) -> bool:
        return self.limiter.allow(tool_name)

    # --- sevkiyat ---------------------------------------------------------
    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Tek JSON-RPC mesajını işler. Bildirimlerde ``None`` döner."""
        method = message.get("method", "")
        request_id = message.get("id")
        is_notification = p.is_notification(message)

        try:
            result = await self._dispatch(method, message, is_notification)
        except p.RPCError as exc:
            if is_notification:
                logger.warning("MCP bildirimi reddedildi: %s — %s", method, exc.message)
                return None
            return exc.to_response(request_id)
        except Exception as exc:  # sürpriz hata kanalı düşürmez
            logger.exception("MCP iç hatası: %s", method)
            if is_notification:
                return None
            return p.error_response(
                request_id,
                p.ErrorCode.INTERNAL_ERROR,
                f"iç hata: {type(exc).__name__}",
            )

        if result is None or is_notification:
            return None
        return p.success_response(request_id, result)

    async def _dispatch(
        self, method: str, message: dict[str, Any], is_notification: bool
    ) -> dict[str, Any] | None:
        if method == "initialize":
            return self._initialize(message)
        if method == "notifications/initialized":
            self.initialized = True
            return None
        if method == "notifications/cancelled":
            return None
        if method == "server/discover":
            version = self._protocol_for(message)
            return self._discover(version)
        if method == "tools/list":
            version = self._require_session(message)
            return self._list_tools(version)
        if method == "tools/call":
            version = self._require_session(message)
            return await self._call_tool(message, version)
        if method == "ping":
            return {}
        if method == "logging/setLevel":
            # İstemci günlük düzeyi ister; sunucu günlüğü zaten stderr'e yazar.
            return {}
        if method in {"resources/list", "resources/read", "prompts/list", "prompts/get"}:
            raise p.RPCError(
                p.ErrorCode.METHOD_NOT_FOUND,
                f"{method}: bu sunucu yalnız 'tools' ilkelini ilan ediyor",
            )
        raise p.RPCError(p.ErrorCode.METHOD_NOT_FOUND, f"bilinmeyen yöntem: {method}")

    def _require_session(self, message: dict[str, Any]) -> str:
        """Sürüm çözümü + legacy oturum zorunluluğu (spec: el sıkışma önce)."""
        declared = p.request_protocol_version(message)
        version = self._protocol_for(message)
        if declared:
            return version  # stateless istek: el sıkışma GEREKMEZ (2026-07-28)
        if not self.initialized:
            raise p.RPCError(
                p.ErrorCode.SERVER_NOT_INITIALIZED,
                "sunucu hazır değil: önce 'initialize' gönderin "
                "(ya da her isteğe _meta.protocolVersion ekleyin)",
            )
        return version

    def _initialize(self, message: dict[str, Any]) -> dict[str, Any]:
        requested = p.request_protocol_version(message)
        version = p.negotiate_version(requested)
        self.session_version = version
        self.initialized = True
        return {
            "protocolVersion": version,
            "capabilities": _capabilities_declaration(),
            "serverInfo": {"name": SERVER_NAME, "version": server_version()},
            "instructions": (
                "Pineal yetenekleri. Her çağrı kasa mandalından ve politika "
                "kapılarından geçer; reddedilen çağrı dürüst bir sebeple döner. "
                "Durum için pineal_status aracını kullanın."
            ),
        }

    def _discover(self, version: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "supportedVersions": list(p.SUPPORTED_PROTOCOL_VERSIONS),
            "capabilities": _capabilities_declaration(),
            "_meta": {p.META_SERVER_INFO_KEY: {"name": SERVER_NAME, "version": server_version()}},
        }
        if version == p.PROTOCOL_VERSION:
            result["resultType"] = "complete"
            result["ttlMs"] = 300_000
            result["cacheScope"] = "public"
        return result

    def _list_tools(self, version: str) -> dict[str, Any]:
        tools = [status_tool_definition(), *build_tools(self.registry)]
        names = [tool["name"] for tool in tools]
        if len(set(names)) != len(names):
            raise p.RPCError(
                p.ErrorCode.INTERNAL_ERROR, "araç adı çakışması: sunucu kendi aracıyla çakışıyor"
            )
        result: dict[str, Any] = {"tools": tools}
        if version == p.PROTOCOL_VERSION:
            result["resultType"] = "complete"
            result["ttlMs"] = 300_000
            result["cacheScope"] = "public"
        return result

    async def _call_tool(self, message: dict[str, Any], version: str) -> dict[str, Any]:
        params = message.get("params") or {}
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise p.RPCError(p.ErrorCode.INVALID_PARAMS, "params.name zorunlu")
        name = name.strip()

        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            # Doğrulama sevkiyattan ÖNCE: durum aracı da sözleşmeye uyar
            # (test yakaladı — aksi halde bozuk argüman sessizce yutulurdu).
            raise p.RPCError(p.ErrorCode.INVALID_PARAMS, "params.arguments nesne olmalı")

        if name == STATUS_TOOL_NAME:
            return await self._status_tool(version)

        index = build_tool_index(self.registry)  # her çağrıda defterden: bayat liste yok
        cap_id = index.get(name)
        if cap_id is None:
            known = ", ".join(sorted({*index, STATUS_TOOL_NAME}))
            raise p.RPCError(
                p.ErrorCode.INVALID_PARAMS,
                f"araç yok: {name!r} — kayıtlı araçlar: {known}",
            )

        if not self._rate_check(name):
            # Sunucunun kendi giriş sınırı: kova dolduysa yetenek hiç koşmaz.
            limited = CapabilityResult(
                capability_id=cap_id,
                available=False,
                unavailable_reason="policy:rate_limited",
                denied_by="rate",
            )
            return render_result(limited, protocol_version=version)

        subject = str(arguments.get("subject") or "")
        state, _snapshot = await self._policy_state(subject=subject)
        ctx = arguments_to_context(arguments)
        result = await self.runner.run(cap_id, ctx, state=state)
        return render_result(result, protocol_version=version)

    async def _status_tool(self, version: str) -> dict[str, Any]:
        state, snapshot = await self._policy_state()
        report = build_status_report(
            self.registry,
            state=state,
            kernel=self.kernel,
            snapshot=snapshot,
            server={
                "name": SERVER_NAME,
                "version": server_version(),
                "protocol_version": version,
                "transport": "stdio",
            },
            rate_limit={
                "limit": self.limiter.limit,
                "window_seconds": self.limiter.window,
            },
        )
        rendered: dict[str, Any] = {
            "content": [{"type": "text", "text": report["text"]}],
            "isError": False,
        }
        if supports_structured_content(version):
            rendered["structuredContent"] = report["structured"]
        if version == p.PROTOCOL_VERSION:
            rendered["resultType"] = "complete"
        return rendered

    # --- stdio taşıması ---------------------------------------------------
    async def serve_stream(self, reader, writer) -> None:
        """NDJSON döngüsü: satır oku → işle → yanıt yaz (yalnız protokol stdout'a)."""
        while True:
            line = await reader()
            if not line:
                return  # EOF: istemci kapattı
            try:
                message = p.parse_message(line)
            except p.RPCError as exc:
                # Zarfta id YOKTU; yanıt id=null ile döner (spec: parse error).
                writer(p.error_response(None, exc.code, exc.message))
                continue
            response = await self.handle(message)
            if response is not None:
                writer(response)


def stdio_main(argv: list[str] | None = None) -> int:
    """stdio sunucusunu koşar (``python -m agent_core.mcp``)."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,  # stdout YALNIZ protokol
        format="[pineal-mcp] %(levelname)s %(message)s",
    )
    for stream in (sys.stdout, sys.stderr):
        try:  # Windows kod sayfası cp1254'te Türkçe/Yunanca karakterler patlamasın
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover - akış yönlendirilmişse
            logger.warning('Suppressed exception observed at agent_core/mcp/server.py:357 (pass)')

    server = MCPServer()

    async def _run() -> None:
        loop = asyncio.get_running_loop()

        def _read_line() -> str:
            data = sys.stdin.buffer.readline()
            if not data:
                return ""
            return data.decode("utf-8", "replace")

        async def reader() -> str:
            return await loop.run_in_executor(None, _read_line)

        def writer(payload: dict[str, Any]) -> None:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        await server.serve_stream(reader, writer)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:  # pragma: no cover - operatör çıkışı
        return 130
    return 0
