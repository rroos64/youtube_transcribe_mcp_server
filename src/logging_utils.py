from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
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


def _next_archive_path(log_path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = log_path.suffix
    stem = log_path.stem or log_path.name
    candidate = log_path.with_name(f"{stem}-{timestamp}{suffix}")
    counter = 1
    while candidate.exists():
        candidate = log_path.with_name(f"{stem}-{timestamp}-{counter}{suffix}")
        counter += 1
    return candidate


def _has_file_handler(logger: logging.Logger, log_path: Path) -> bool:
    target = str(log_path.resolve())
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            if getattr(handler, "baseFilename", None) == target:
                return True
    return False


def configure_file_logging(log_dir: Path, filename: str = "logs.txt") -> Path | None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log_warning("log_dir_unavailable", dir=str(log_dir), error=str(exc))
        return None

    log_path = (log_dir / filename).resolve()
    if log_path.exists():
        archive_path = _next_archive_path(log_path)
        try:
            log_path.rename(archive_path)
        except OSError as exc:
            log_warning(
                "log_archive_failed",
                path=str(log_path),
                archive=str(archive_path),
                error=str(exc),
            )

    if _has_file_handler(_logger, log_path):
        return log_path

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logger.addHandler(handler)
    return log_path
