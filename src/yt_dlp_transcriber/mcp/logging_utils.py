from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger("yt_dlp_transcriber")


def log_event(event: str, **fields: Any) -> None:
    if not _logger.isEnabledFor(logging.INFO):
        return

    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")

    if parts:
        _logger.info("%s %s", event, " ".join(parts))
    else:
        _logger.info("%s", event)
