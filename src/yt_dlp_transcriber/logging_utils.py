from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger("yt_dlp_transcriber")


def _log(level: int, event: str, **fields: Any) -> None:
    if not _logger.isEnabledFor(level):
        return

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
