from __future__ import annotations

from datetime import datetime


def parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = value[:-1] if value.endswith("Z") else value
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
