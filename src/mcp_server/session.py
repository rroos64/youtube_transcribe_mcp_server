from __future__ import annotations

from typing import Any

from domain.types import SessionId


def extract_session_id(ctx: Any | None) -> str | None:
    if ctx is None:
        return None

    if isinstance(ctx, dict):
        for key in ("mcp-session-id", "mcp_session_id", "session_id", "sessionId"):
            val = ctx.get(key)
            if val:
                return str(val)

    for attr in ("session_id", "sessionId"):
        val = getattr(ctx, attr, None)
        if val:
            return str(val)

    headers = None
    if hasattr(ctx, "headers"):
        headers = getattr(ctx, "headers", None)
    elif hasattr(ctx, "request"):
        headers = getattr(getattr(ctx, "request", None), "headers", None)

    if headers is not None:
        for key in ("mcp-session-id", "MCP-Session-Id", "x-mcp-session-id"):
            if hasattr(headers, "get"):
                val = headers.get(key)
                if val:
                    return str(val)
    return None


def get_session_id(
    *,
    session_id: str | None = None,
    ctx: Any | None = None,
    default_session_id: str = "",
    required: bool = True,
) -> SessionId | None:
    ctx_id = extract_session_id(ctx)
    if session_id and ctx_id and session_id != ctx_id:
        raise ValueError("session_id does not match mcp-session-id header")
    if session_id:
        return SessionId(session_id)
    if ctx_id:
        return SessionId(ctx_id)
    if default_session_id:
        return SessionId(default_session_id)
    if required:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")
    return None
