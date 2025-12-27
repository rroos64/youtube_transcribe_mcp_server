from __future__ import annotations

import os

from config import AppConfig
from mcp_server.app import mcp
from mcp_server import resources as _resources
from mcp_server import templates as _templates
from mcp_server import tools as _tools
from logging_utils import configure_file_logging

__all__ = ["mcp"]

# Import side effects register MCP handlers.
_resources, _templates, _tools


if __name__ == "__main__":
    config = AppConfig.from_env()
    configure_file_logging(config.data_dir)
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        path="/mcp",
        stateless_http=True,
    )
