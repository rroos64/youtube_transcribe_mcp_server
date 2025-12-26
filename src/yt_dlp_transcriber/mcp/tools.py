from __future__ import annotations

import re
from typing import Any

from yt_dlp_transcriber.domain.models import ManifestItem, TranscriptFormat

from .app import mcp
from .deps import get_services
from .error_handling import handle_mcp_errors
from .session import get_session_id
from yt_dlp_transcriber.logging_utils import log_debug, log_event, log_warning

_YT_URL_RE = re.compile(r"^https?://(www\.)?youtube\.com/watch\?v=|^https?://youtu\.be/")


def _is_youtube_url(url: str) -> bool:
    return bool(_YT_URL_RE.search(url))


def _parse_format(fmt: str) -> TranscriptFormat:
    try:
        return TranscriptFormat(fmt)
    except ValueError as exc:
        log_warning("invalid_format", fmt=fmt)
        raise ValueError("fmt must be one of: txt, vtt, jsonl") from exc


def _item_payload(item: ManifestItem, session_id: str) -> dict:
    payload = item.to_dict()
    payload["session_id"] = session_id
    return payload


@handle_mcp_errors
def youtube_transcribe(url: str) -> str:
    if not _is_youtube_url(url):
        log_warning("invalid_youtube_url", url=url)
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")

    services = get_services()
    log_event("youtube_transcribe", url=url)
    return services.transcription_service.transcribe_to_text(url)


@handle_mcp_errors
def youtube_transcribe_to_file(
    url: str,
    fmt: str = "txt",
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    if not _is_youtube_url(url):
        log_warning("invalid_youtube_url", url=url)
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")
    format_enum = _parse_format(fmt)

    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event("youtube_transcribe_to_file", session_id=str(sid), url=url, fmt=fmt)
    item = services.transcription_service.transcribe_to_file(
        url=url,
        fmt=format_enum,
        session_id=sid,
    )
    return _item_payload(item, str(sid))


@handle_mcp_errors
def youtube_get_duration(url: str) -> dict:
    if not _is_youtube_url(url):
        log_warning("invalid_youtube_url", url=url)
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")

    services = get_services()
    log_event("youtube_get_duration", url=url)
    info = services.ytdlp_client.get_info(url)
    return {
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string"),
        "title": info.get("title"),
        "is_live": info.get("is_live"),
    }


@handle_mcp_errors
def youtube_transcribe_auto(
    url: str,
    fmt: str = "txt",
    max_text_bytes: int | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    if not _is_youtube_url(url):
        log_warning("invalid_youtube_url", url=url)
        raise ValueError("Please provide a valid YouTube video URL (youtube.com/watch?v=... or youtu.be/...).")
    format_enum = _parse_format(fmt)

    services = get_services()
    if max_text_bytes is None:
        max_text_bytes = services.config.auto_text_max_bytes

    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
        required=False,
    )

    log_event(
        "youtube_transcribe_auto",
        session_id=str(sid) if sid else None,
        url=url,
        fmt=fmt,
        max_text_bytes=max_text_bytes,
    )
    result = services.transcription_service.transcribe_auto(
        url=url,
        fmt=format_enum,
        max_text_bytes=max_text_bytes,
        session_id=sid,
    )

    payload = {
        "kind": result.kind,
        "bytes": result.bytes,
        "duration": result.info.duration,
        "duration_string": result.info.duration_string,
        "title": result.info.title,
        "is_live": result.info.is_live,
    }
    if result.kind == "text":
        log_debug("youtube_transcribe_auto.text", bytes=result.bytes)
        payload["text"] = result.text
        return payload

    item = result.item
    if item is None or sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_debug("youtube_transcribe_auto.file", item_id=str(item.id), bytes=result.bytes)
    payload.update(_item_payload(item, str(sid)))
    return payload


@handle_mcp_errors
def list_session_items(
    kind: str | None = None,
    format: str | None = None,
    pinned: bool | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event(
        "list_session_items",
        session_id=str(sid),
        kind=kind,
        format=format,
        pinned=pinned,
    )
    items = services.session_service.list_items(
        sid,
        kind=kind,
        format=format,
        pinned=pinned,
    )
    return {"session_id": str(sid), "items": [item.to_dict() for item in items]}


@handle_mcp_errors
def pin_item(item_id: str, session_id: str | None = None, ctx: Any | None = None) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event("pin_item", session_id=str(sid), item_id=item_id)
    item = services.session_service.pin_item(item_id, session_id=sid)
    return item.to_dict()


@handle_mcp_errors
def unpin_item(item_id: str, session_id: str | None = None, ctx: Any | None = None) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event("unpin_item", session_id=str(sid), item_id=item_id)
    item = services.session_service.unpin_item(item_id, session_id=sid)
    return item.to_dict()


@handle_mcp_errors
def set_item_ttl(
    item_id: str,
    ttl_seconds: int,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event("set_item_ttl", session_id=str(sid), item_id=item_id, ttl_seconds=ttl_seconds)
    item = services.session_service.set_item_ttl(item_id, ttl_seconds, session_id=sid)
    return item.to_dict()


@handle_mcp_errors
def delete_item(item_id: str, session_id: str | None = None, ctx: Any | None = None) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event("delete_item", session_id=str(sid), item_id=item_id)
    services.session_service.delete_item(item_id, session_id=sid)
    return {"deleted": True, "id": item_id}


@handle_mcp_errors
def write_text_file(
    relpath: str,
    content: str,
    overwrite: bool = False,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event(
        "write_text_file",
        session_id=str(sid),
        relpath=relpath,
        overwrite=overwrite,
    )
    item = services.session_service.write_text_file(
        relpath=relpath,
        content=content,
        overwrite=overwrite,
        session_id=sid,
    )
    return _item_payload(item, str(sid))


@handle_mcp_errors
def read_file_info(
    item_id: str | None = None,
    relpath: str | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event(
        "read_file_info",
        session_id=str(sid),
        item_id=item_id,
        relpath=relpath,
    )
    info = services.session_service.read_file_info(
        session_id=sid,
        item_id=item_id,
        relpath=relpath,
    )
    return {
        "id": str(info.id) if info.id else None,
        "session_id": str(info.session_id),
        "path": str(info.path),
        "relpath": info.relpath,
        "size": info.size,
        "pinned": info.pinned,
        "expires_at": info.expires_at,
        "format": info.format if info.format else None,
        "kind": info.kind.value if info.kind else None,
    }


@handle_mcp_errors
def read_file_chunk(
    offset: int = 0,
    max_bytes: int = 200000,
    item_id: str | None = None,
    relpath: str | None = None,
    session_id: str | None = None,
    ctx: Any | None = None,
) -> dict:
    services = get_services()
    sid = get_session_id(
        session_id=session_id,
        ctx=ctx,
        default_session_id=services.config.default_session_id,
    )
    if sid is None:
        raise ValueError("session_id is required (pass session_id or set mcp-session-id header)")

    log_event(
        "read_file_chunk",
        session_id=str(sid),
        item_id=item_id,
        relpath=relpath,
        offset=offset,
        max_bytes=max_bytes,
    )
    chunk = services.session_service.read_file_chunk(
        session_id=sid,
        offset=offset,
        max_bytes=max_bytes,
        item_id=item_id,
        relpath=relpath,
    )
    return {
        "data": chunk.data,
        "next_offset": chunk.next_offset,
        "eof": chunk.eof,
        "size": chunk.size,
        "path": str(chunk.path),
        "id": str(chunk.id) if chunk.id else None,
    }


mcp.tool(youtube_transcribe)
mcp.tool(youtube_transcribe_to_file)
mcp.tool(youtube_get_duration)
mcp.tool(youtube_transcribe_auto)
mcp.tool(list_session_items)
mcp.tool(pin_item)
mcp.tool(unpin_item)
mcp.tool(set_item_ttl)
mcp.tool(delete_item)
mcp.tool(write_text_file)
mcp.tool(read_file_info)
mcp.tool(read_file_chunk)
