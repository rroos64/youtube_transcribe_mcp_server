from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from yt_dlp_transcriber.domain.errors import (
    ExpiredItemError,
    ExternalCommandError,
    InvalidItemId,
    InvalidSessionId,
    NotFoundError,
)
from yt_dlp_transcriber.logging_utils import log_error, log_warning

F = TypeVar("F", bound=Callable[..., Any])


def handle_mcp_errors(func: F) -> F:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except InvalidSessionId as exc:
            log_warning("invalid_session_id", error=str(exc))
            raise ValueError(f"Invalid session_id. {exc}") from exc
        except InvalidItemId as exc:
            log_warning("invalid_item_id", error=str(exc))
            raise ValueError(f"Invalid item_id. {exc}") from exc
        except NotFoundError as exc:
            log_warning("not_found", error=str(exc))
            raise ValueError(str(exc)) from exc
        except ExpiredItemError as exc:
            log_warning("expired_item", error=str(exc))
            raise ValueError("Item expired") from exc
        except ExternalCommandError as exc:
            log_error("external_command_failed", error=str(exc))
            raise RuntimeError("External command failed. Check server logs for details.") from exc

    return wrapper  # type: ignore[return-value]
