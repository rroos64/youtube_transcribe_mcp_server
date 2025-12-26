from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.domain.models import ItemKind, ManifestItem, TranscriptFormat
from yt_dlp_transcriber.domain.types import ItemId, SessionId


@dataclass(frozen=True)
class FileInfo:
    id: ItemId | None
    session_id: SessionId
    path: Path
    relpath: str
    size: int
    pinned: bool | None
    expires_at: str | None
    format: TranscriptFormat | None
    kind: ItemKind | None


@dataclass(frozen=True)
class FileChunk:
    data: str
    next_offset: int
    eof: bool
    size: int
    path: Path
    id: ItemId | None


def _expires_at(ttl_seconds: int) -> str:
    return (datetime.utcnow() + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat() + "Z"


def _coerce_session_id(session_id: SessionId | str) -> SessionId:
    if isinstance(session_id, SessionId):
        return session_id
    return SessionId(str(session_id))


def _coerce_item_id(item_id: ItemId | str | None) -> ItemId | None:
    if item_id is None:
        return None
    if isinstance(item_id, ItemId):
        return item_id
    return ItemId(str(item_id))


class SessionService:
    def __init__(self, store: SessionStore, repo: ManifestRepository) -> None:
        self._store = store
        self._repo = repo

    def list_items(
        self,
        session_id: SessionId | str,
        *,
        kind: ItemKind | None = None,
        format: TranscriptFormat | None = None,
        pinned: bool | None = None,
    ) -> list[ManifestItem]:
        sid = _coerce_session_id(session_id)
        self._repo.cleanup_session(sid)
        return self._repo.list_items(sid, kind=kind, format=format, pinned=pinned)

    def pin_item(self, item_id: ItemId | str, *, session_id: SessionId | str) -> ManifestItem:
        sid = _coerce_session_id(session_id)
        target_id = _coerce_item_id(item_id)
        self._repo.cleanup_session(sid)
        return self._update_item(
            sid,
            target_id,
            lambda item: replace(item, pinned=True, expires_at=None),
        )

    def unpin_item(self, item_id: ItemId | str, *, session_id: SessionId | str) -> ManifestItem:
        sid = _coerce_session_id(session_id)
        target_id = _coerce_item_id(item_id)
        self._repo.cleanup_session(sid)
        return self._update_item(
            sid,
            target_id,
            lambda item: replace(item, pinned=False, expires_at=_expires_at(self._repo.default_ttl_sec)),
        )

    def set_item_ttl(
        self,
        item_id: ItemId | str,
        ttl_seconds: int,
        *,
        session_id: SessionId | str,
    ) -> ManifestItem:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")
        sid = _coerce_session_id(session_id)
        target_id = _coerce_item_id(item_id)
        self._repo.cleanup_session(sid)
        return self._update_item(
            sid,
            target_id,
            lambda item: replace(item, pinned=False, expires_at=_expires_at(ttl_seconds)),
        )

    def delete_item(self, item_id: ItemId | str, *, session_id: SessionId | str) -> bool:
        sid = _coerce_session_id(session_id)
        target_id = _coerce_item_id(item_id)
        self._repo.cleanup_session(sid)
        manifest = self._repo.load(sid)
        updated_items: list[ManifestItem] = []
        deleted = False
        for item in manifest.items:
            if item.id == target_id:
                deleted = True
                try:
                    path = self._store.resolve_relpath(sid, item.relpath)
                    if path.exists():
                        path.unlink()
                except (OSError, ValueError):
                    pass
                continue
            updated_items.append(item)

        if not deleted:
            raise ValueError("Item not found")

        self._repo.save(replace(manifest, items=updated_items))
        return True

    def read_file_info(
        self,
        *,
        session_id: SessionId | str,
        item_id: ItemId | str | None = None,
        relpath: str | None = None,
    ) -> FileInfo:
        if not item_id and not relpath:
            raise ValueError("Provide either item_id or relpath")
        sid = _coerce_session_id(session_id)
        target_id = _coerce_item_id(item_id)
        self._repo.cleanup_session(sid)
        manifest = self._repo.load(sid)

        item = self._find_item(manifest.items, target_id, relpath)
        if item:
            path = self._store.resolve_relpath(sid, item.relpath)
            size = path.stat().st_size
            updated = replace(item, size=size)
            self._save_item(manifest, updated)
            return FileInfo(
                id=updated.id,
                session_id=sid,
                path=path,
                relpath=updated.relpath,
                size=size,
                pinned=updated.pinned,
                expires_at=updated.expires_at,
                format=updated.format,
                kind=updated.kind,
            )

        if relpath:
            path = self._store.resolve_relpath(sid, relpath)
            size = path.stat().st_size
            return FileInfo(
                id=None,
                session_id=sid,
                path=path,
                relpath=relpath,
                size=size,
                pinned=None,
                expires_at=None,
                format=None,
                kind=None,
            )

        raise ValueError("Item not found")

    def read_file_chunk(
        self,
        *,
        session_id: SessionId | str,
        offset: int = 0,
        max_bytes: int = 200000,
        item_id: ItemId | str | None = None,
        relpath: str | None = None,
    ) -> FileChunk:
        if not item_id and not relpath:
            raise ValueError("Provide either item_id or relpath")
        if max_bytes < 1 or max_bytes > 200000:
            raise ValueError("max_bytes must be between 1 and 200000")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        sid = _coerce_session_id(session_id)
        target_id = _coerce_item_id(item_id)
        self._repo.cleanup_session(sid)
        manifest = self._repo.load(sid)
        item = self._find_item(manifest.items, target_id, relpath)

        if item:
            path = self._store.resolve_relpath(sid, item.relpath)
        elif relpath:
            path = self._store.resolve_relpath(sid, relpath)
        else:
            raise ValueError("Item not found")

        if not path.exists():
            raise ValueError(f"File does not exist: {path}")

        size = path.stat().st_size
        if offset >= size:
            return FileChunk(
                data="",
                next_offset=offset,
                eof=True,
                size=size,
                path=path,
                id=item.id if item else None,
            )

        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(max_bytes)

        next_offset = offset + len(chunk)
        eof = next_offset >= size
        return FileChunk(
            data=chunk.decode("utf-8", errors="replace"),
            next_offset=next_offset,
            eof=eof,
            size=size,
            path=path,
            id=item.id if item else None,
        )

    def _find_item(
        self,
        items: list[ManifestItem],
        item_id: ItemId | None,
        relpath: str | None,
    ) -> ManifestItem | None:
        for item in items:
            if item_id and item.id == item_id:
                return item
            if relpath and item.relpath == relpath:
                return item
        return None

    def _save_item(self, manifest, item: ManifestItem) -> None:
        updated_items = [item if entry.id == item.id else entry for entry in manifest.items]
        self._repo.save(replace(manifest, items=updated_items))

    def _update_item(
        self,
        session_id: SessionId,
        item_id: ItemId,
        updater,
    ) -> ManifestItem:
        manifest = self._repo.load(session_id)
        updated_items: list[ManifestItem] = []
        updated_item: ManifestItem | None = None

        for item in manifest.items:
            if item.id == item_id:
                updated_item = updater(item)
                updated_items.append(updated_item)
            else:
                updated_items.append(item)

        if updated_item is None:
            raise ValueError("Item not found")

        self._repo.save(replace(manifest, items=updated_items))
        return updated_item
