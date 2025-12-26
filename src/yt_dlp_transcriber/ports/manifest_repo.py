from __future__ import annotations

from typing import Protocol

from yt_dlp_transcriber.domain.models import ItemKind, Manifest, ManifestItem, TranscriptFormat
from yt_dlp_transcriber.domain.types import SessionId


class ManifestRepositoryPort(Protocol):
    @property
    def default_ttl_sec(self) -> int:
        ...

    def load(self, session_id: SessionId | str) -> Manifest:
        ...

    def save(self, manifest: Manifest) -> None:
        ...

    def add_item(
        self,
        *,
        session_id: SessionId | str,
        kind: ItemKind,
        fmt: TranscriptFormat | str,
        relpath: str,
        pinned: bool,
        ttl_seconds: int,
    ) -> ManifestItem:
        ...

    def list_items(
        self,
        session_id: SessionId | str,
        *,
        kind: ItemKind | str | None = None,
        format: TranscriptFormat | str | None = None,
        pinned: bool | None = None,
    ) -> list[ManifestItem]:
        ...

    def cleanup_session(self, session_id: SessionId | str) -> int:
        ...
