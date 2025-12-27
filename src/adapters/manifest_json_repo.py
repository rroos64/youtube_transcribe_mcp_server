from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from adapters.filesystem_store import SessionStore
from domain.models import ItemKind, Manifest, ManifestItem, TranscriptFormat
from domain.time_utils import parse_iso_timestamp
from domain.types import ItemId, SessionId, coerce_session_id
from ports.clock import ClockPort, SystemClock


def _now_iso(now: datetime) -> str:
    return now.replace(microsecond=0).isoformat() + "Z"


def _expires_at(ttl_seconds: int, now: datetime) -> str:
    return (now + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat() + "Z"


def _item_sort_key(item: ManifestItem) -> tuple[datetime, str]:
    ts = parse_iso_timestamp(item.created_at) or datetime.min
    return ts, str(item.id)


class ManifestRepository:
    def __init__(
        self,
        store: SessionStore,
        *,
        default_ttl_sec: int,
        max_session_items: int = 0,
        max_session_bytes: int = 0,
        use_lock: bool = False,
        clock: ClockPort | None = None,
    ) -> None:
        self._store = store
        self._default_ttl_sec = default_ttl_sec
        self._max_session_items = max_session_items
        self._max_session_bytes = max_session_bytes
        self._use_lock = use_lock
        self._clock = clock or SystemClock()

    @property
    def default_ttl_sec(self) -> int:
        return self._default_ttl_sec

    def load(self, session_id: SessionId | str) -> Manifest:
        sid = coerce_session_id(session_id)
        path = self._store.manifest_path(sid)
        data: dict[str, Any]
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        else:
            data = {}

        if not isinstance(data, dict):
            data = {}

        created_at = str(data.get("created_at") or _now_iso(self._clock.now()))
        raw_items = data.get("items", [])
        items: list[ManifestItem] = []
        if isinstance(raw_items, list):
            for raw in raw_items:
                if isinstance(raw, Mapping):
                    try:
                        items.append(ManifestItem.from_dict(raw))
                    except ValueError:
                        continue

        return Manifest(session_id=sid, created_at=created_at, items=items)

    def save(self, manifest: Manifest) -> None:
        path = self._store.manifest_path(manifest.session_id)
        payload = manifest.to_dict()
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = path.with_name(f"{path.name}.tmp")
        with self._locked_file(path):
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)

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
        sid = coerce_session_id(session_id)
        manifest = self.load(sid)
        item_id = ItemId(f"tr_{uuid.uuid4().hex}")
        now = self._clock.now()
        created_at = _now_iso(now)
        expires_at = None if pinned else _expires_at(ttl_seconds, now=now)
        target = self._store.resolve_relpath(sid, relpath)
        size = target.stat().st_size

        format_value = fmt.value if isinstance(fmt, TranscriptFormat) else str(fmt)
        item = ManifestItem(
            id=item_id,
            kind=kind,
            format=format_value,
            relpath=relpath,
            size=size,
            created_at=created_at,
            expires_at=expires_at,
            pinned=pinned,
        )
        updated = replace(manifest, items=[*manifest.items, item])
        self.save(updated)
        self.cleanup_session(sid)
        return item

    def list_items(
        self,
        session_id: SessionId | str,
        *,
        kind: ItemKind | str | None = None,
        format: TranscriptFormat | str | None = None,
        pinned: bool | None = None,
    ) -> list[ManifestItem]:
        manifest = self.load(session_id)
        items = manifest.items
        if kind is not None:
            if isinstance(kind, ItemKind):
                items = [item for item in items if item.kind is kind]
            else:
                items = [item for item in items if item.kind.value == str(kind)]
        if format is not None:
            format_value = format.value if isinstance(format, TranscriptFormat) else str(format)
            items = [item for item in items if str(item.format) == format_value]
        if pinned is not None:
            items = [item for item in items if item.pinned is pinned]
        return items

    def cleanup_session(self, session_id: SessionId | str) -> int:
        sid = coerce_session_id(session_id)
        manifest = self.load(sid)
        kept: list[ManifestItem] = []
        removed = 0
        changed = False
        now = self._clock.now()

        for item in manifest.items:
            if not item.relpath:
                changed = True
                continue

            try:
                target = self._store.resolve_relpath(sid, item.relpath)
            except ValueError:
                changed = True
                continue

            if not target.exists():
                changed = True
                removed += 1
                continue

            updated = item
            expires_at = item.expires_at
            expires_dt = parse_iso_timestamp(expires_at)

            if not item.pinned:
                if expires_dt is None:
                    expires_at = _expires_at(self._default_ttl_sec, now=now)
                    updated = replace(updated, expires_at=expires_at)
                    expires_dt = parse_iso_timestamp(expires_at)
                    changed = True

                if expires_dt and now >= expires_dt:
                    try:
                        target.unlink()
                    except OSError:
                        pass
                    removed += 1
                    changed = True
                    continue

            size = target.stat().st_size
            if size != updated.size:
                updated = replace(updated, size=size)
                changed = True

            kept.append(updated)

        if self._max_session_items > 0 or self._max_session_bytes > 0:
            total_size = sum(item.size for item in kept)
            removable = sorted([i for i in kept if not i.pinned], key=_item_sort_key)
            while removable and (
                (self._max_session_items > 0 and len(kept) > self._max_session_items)
                or (self._max_session_bytes > 0 and total_size > self._max_session_bytes)
            ):
                victim = removable.pop(0)
                try:
                    vp = self._store.resolve_relpath(sid, victim.relpath)
                    if vp.exists():
                        vp.unlink()
                except (OSError, ValueError):
                    pass
                total_size -= victim.size
                kept.remove(victim)
                removed += 1
                changed = True

        if changed:
            self.save(replace(manifest, items=kept))

        return removed

    @contextmanager
    def _locked_file(self, path: Path):
        if not self._use_lock:
            yield None
            return
        try:
            import fcntl
        except ImportError:
            yield None
            return

        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
