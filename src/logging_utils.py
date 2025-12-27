from __future__ import annotations

import contextlib
import logging
import uuid
from contextvars import ContextVar
from typing import Any

_logger = logging.getLogger("yt_dlp_transcriber")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


@contextlib.contextmanager
def request_context(request_id: str | None = None):
    if request_id is None:
        request_id = get_request_id() or uuid.uuid4().hex
    token = _request_id.set(request_id)
    try:
        yield request_id
    finally:
        _request_id.reset(token)


def _log(level: int, event: str, **fields: Any) -> None:
    if not _logger.isEnabledFor(level):
        return

    if fields.get("request_id") is None:
        ctx_request_id = get_request_id()
        if ctx_request_id is not None:
            fields = {**fields, "request_id": ctx_request_id}

    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")

    if parts:
        _logger.log(level, "%s %s", event, " ".join(parts))
    else:
        _logger.log(level, "%s", event)


def log_debug(event: str, **fields: Any) -> None:
    _log(logging.DEBUG, event, **fields)


def log_info(event: str, **fields: Any) -> None:
    _log(logging.INFO, event, **fields)


def log_warning(event: str, **fields: Any) -> None:
    _log(logging.WARNING, event, **fields)


def log_error(event: str, **fields: Any) -> None:
    _log(logging.ERROR, event, **fields)


def log_event(event: str, **fields: Any) -> None:
    log_info(event, **fields)
