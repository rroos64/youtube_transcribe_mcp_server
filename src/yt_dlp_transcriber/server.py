from __future__ import annotations

import os

from yt_dlp_transcriber.mcp.app import mcp
from yt_dlp_transcriber.mcp import resources as _resources
from yt_dlp_transcriber.mcp import templates as _templates
from yt_dlp_transcriber.mcp import tools as _tools

__all__ = ["mcp"]

# Import side effects register MCP handlers.
_resources, _templates, _tools


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        path="/mcp",
        stateless_http=True,
    )
