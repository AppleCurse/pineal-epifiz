"""``python -m agent_core.mcp`` — MCP stdio sunucusu giriş noktası."""

from __future__ import annotations

import sys

from agent_core.mcp.server import stdio_main

if __name__ == "__main__":
    sys.exit(stdio_main(sys.argv[1:]))
