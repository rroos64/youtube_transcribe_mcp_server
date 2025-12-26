from __future__ import annotations

import re
from dataclasses import dataclass

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_id(value: str, name: str) -> str:
    if not value or not _ID_RE.match(value):
        raise ValueError(f"{name} must be 1-64 chars of letters, numbers, '-' or '_'")
    return value


@dataclass(frozen=True)
class SessionId:
    value: str

    def __post_init__(self) -> None:
        _validate_id(self.value, "session_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ItemId:
    value: str

    def __post_init__(self) -> None:
        _validate_id(self.value, "item_id")

    def __str__(self) -> str:
        return self.value
