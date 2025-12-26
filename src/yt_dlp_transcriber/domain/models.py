from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from yt_dlp_transcriber.domain.types import ItemId, SessionId


class TranscriptFormat(str, Enum):
    TXT = "txt"
    VTT = "vtt"
    JSONL = "jsonl"


class ItemKind(str, Enum):
    TRANSCRIPT = "transcript"
    DERIVED = "derived"


@dataclass(frozen=True)
class ManifestItem:
    id: ItemId
    kind: ItemKind
    format: TranscriptFormat
    relpath: str
    size: int
    created_at: str
    expires_at: str | None
    pinned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "kind": self.kind.value,
            "format": self.format.value,
            "relpath": self.relpath,
            "size": self.size,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "pinned": self.pinned,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ManifestItem":
        return cls(
            id=ItemId(str(data.get("id", ""))),
            kind=ItemKind(str(data.get("kind", ItemKind.TRANSCRIPT.value))),
            format=TranscriptFormat(str(data.get("format", TranscriptFormat.TXT.value))),
            relpath=str(data.get("relpath", "")),
            size=int(data.get("size", 0)),
            created_at=str(data.get("created_at", "")),
            expires_at=data.get("expires_at"),
            pinned=bool(data.get("pinned")),
        )


@dataclass(frozen=True)
class Manifest:
    session_id: SessionId
    created_at: str
    items: list[ManifestItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "created_at": self.created_at,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Manifest":
        raw_items = data.get("items", [])
        items: list[ManifestItem] = []
        if isinstance(raw_items, list):
            for raw in raw_items:
                if isinstance(raw, Mapping):
                    items.append(ManifestItem.from_dict(raw))
        return cls(
            session_id=SessionId(str(data.get("session_id", ""))),
            created_at=str(data.get("created_at", "")),
            items=items,
        )
