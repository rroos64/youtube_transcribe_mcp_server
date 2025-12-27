from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from domain.errors import (
    ExpiredItemError,
    ExternalCommandError,
    InvalidItemId,
    InvalidSessionId,
    NotFoundError,
)
from logging_utils import log_error, log_warning, request_context

F = TypeVar("F", bound=Callable[..., Any])


def handle_mcp_errors(func: F) -> F:
    @wraps(func)
    def wrapper(*args, **kwargs):
        with request_context():
            try:
                return func(*args, **kwargs)
            except InvalidSessionId as exc:
                log_warning("invalid_session_id", error=str(exc))
                raise ValueError(f"ERR_INVALID_SESSION: Invalid session_id. {exc}") from exc
            except InvalidItemId as exc:
                log_warning("invalid_item_id", error=str(exc))
                raise ValueError(f"ERR_INVALID_ITEM: Invalid item_id. {exc}") from exc
            except NotFoundError as exc:
                log_warning("not_found", error=str(exc))
                raise ValueError(f"ERR_NOT_FOUND: {exc}") from exc
            except ExpiredItemError as exc:
                log_warning("expired_item", error=str(exc))
                raise ValueError("ERR_EXPIRED_ITEM: Item expired") from exc
            except ExternalCommandError as exc:
                log_error("external_command_failed", error=str(exc))
                raise RuntimeError(
                    "ERR_EXTERNAL_COMMAND: External command failed. Check server logs for details."
                ) from exc

    return wrapper  # type: ignore[return-value]
