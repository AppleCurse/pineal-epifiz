"""FAZ D · D1 — MCP (Model Context Protocol) ihracı.

Pineal'in yetenekleri artık yalnız içeride değil: ``CapabilityRegistry``'deki
her yetenek standart MCP araçları olarak yayınlanır. Çağrılar içerideki
yeteneklerle AYNI kapılardan geçer (kasa · hız · ENABLE_* · çocuk kilidi) —
dışarısı için ayrı bir yol yoktur.

Çalıştırma::

    python -m agent_core.mcp              # stdio sunucusu (MCP istemcileri)

Programatik kullanım::

    from agent_core.mcp import MCPServer, protocol
    server = MCPServer()
    yanit = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
"""

from __future__ import annotations

from agent_core.mcp import protocol  # noqa: F401  (yeniden ihracat)
from agent_core.mcp.server import MCPServer, SERVER_NAME, server_version  # noqa: F401
from agent_core.mcp.tools import build_tools, tool_name_for  # noqa: F401

__all__ = [
    "MCPServer",
    "SERVER_NAME",
    "build_tools",
    "protocol",
    "server_version",
    "tool_name_for",
]
