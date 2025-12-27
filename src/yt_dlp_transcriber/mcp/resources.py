from __future__ import annotations

import json
import urllib.parse
from datetime import datetime
from typing import Any
from dataclasses import replace

from yt_dlp_transcriber.domain.errors import NotFoundError
from yt_dlp_transcriber.domain.models import ItemKind
from yt_dlp_transcriber.domain.time_utils import parse_iso_timestamp

from .app import mcp
from .deps import get_services
from .error_handling import handle_mcp_errors
from yt_dlp_transcriber.logging_utils import log_event, log_warning
from .session import get_session_id


def _item_sort_key(item) -> tuple[datetime, str]:
    ts = parse_iso_timestamp(item.created_at) or datetime.min
    return ts, str(item.id)


@handle_mcp_errors
def resource_session_index(session_id: str, ctx: Any | None = None) -> str:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")
    log_event("resource_session_index", session_id=str(sid))
    services.manifest_repo.cleanup_session(sid)
    manifest = services.manifest_repo.load(sid)
    return json.dumps(manifest.to_dict(), ensure_ascii=False)


@handle_mcp_errors
def resource_session_latest(session_id: str, ctx: Any | None = None) -> str:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")
    log_event("resource_session_latest", session_id=str(sid))
    services.manifest_repo.cleanup_session(sid)
    manifest = services.manifest_repo.load(sid)
    items = [item for item in manifest.items if item.kind is ItemKind.TRANSCRIPT]
    items.sort(key=_item_sort_key)
    latest = items[-1] if items else None
    payload = {"session_id": str(sid), "item": latest.to_dict() if latest else None}
    return json.dumps(payload, ensure_ascii=False)


@handle_mcp_errors
def resource_session_item(session_id: str, item_id: str, ctx: Any | None = None) -> str:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")
    log_event("resource_session_item", session_id=str(sid), item_id=item_id)
    services.manifest_repo.cleanup_session(sid)
    item_id = urllib.parse.unquote(item_id)
    manifest = services.manifest_repo.load(sid)

    item = None
    for entry in manifest.items:
        if str(entry.id) == item_id:
            item = entry
            break
    if not item:
        raise NotFoundError("Item not found")

    path = services.store.resolve_relpath(sid, item.relpath)
    size = path.stat().st_size
    if size != item.size:
        updated = replace(item, size=size)
        manifest_items = [updated if entry.id == item.id else entry for entry in manifest.items]
        services.manifest_repo.save(replace(manifest, items=manifest_items))
        item = updated

    content = None
    truncated = False
    if size <= services.config.inline_text_max_bytes:
        content = path.read_text(encoding="utf-8", errors="replace")
    else:
        truncated = True
        log_warning(
            "resource_session_item.truncated",
            session_id=str(sid),
            item_id=item_id,
            size=size,
            inline_max=services.config.inline_text_max_bytes,
        )

    payload = {
        "session_id": str(sid),
        "item": item.to_dict(),
        "content": content,
        "truncated": truncated,
        "inline_max_bytes": services.config.inline_text_max_bytes,
    }
    return json.dumps(payload, ensure_ascii=False)


mcp.resource("transcripts://session/{session_id}/index")(resource_session_index)
mcp.resource("transcripts://session/{session_id}/latest")(resource_session_latest)
mcp.resource("transcripts://session/{session_id}/item/{item_id}")(resource_session_item)
