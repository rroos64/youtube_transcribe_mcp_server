from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import (
    ManifestRepository,
    _item_sort_key,
    _parse_ts,
)
from yt_dlp_transcriber.domain.models import ItemKind, ManifestItem, TranscriptFormat
from yt_dlp_transcriber.domain.types import ItemId, SessionId


def _make_item(*, item_id: str, relpath: str, size: int, pinned: bool, expires_at: str | None) -> ManifestItem:
    return ManifestItem(
        id=ItemId(item_id),
        kind=ItemKind.TRANSCRIPT,
        format=TranscriptFormat.TXT.value,
        relpath=relpath,
        size=size,
        created_at="2024-01-01T00:00:00Z",
        expires_at=expires_at,
        pinned=pinned,
    )


def test_load_handles_invalid_json_and_non_dict(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_load")
    path = store.manifest_path(session_id)

    path.write_text("{bad json", encoding="utf-8")
    manifest = repo.load(session_id)
    assert manifest.items == []

    path.write_text("[]", encoding="utf-8")
    manifest = repo.load(session_id)
    assert manifest.items == []


def test_load_skips_invalid_items(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_invalid_items")
    path = store.manifest_path(session_id)

    payload = {
        "created_at": "2024-01-01T00:00:00Z",
        "items": [
            {"id": "", "kind": "transcript", "format": "txt", "relpath": "x", "size": 1},
            {
                "id": "tr_valid",
                "kind": "transcript",
                "format": "txt",
                "relpath": "transcripts/ok.txt",
                "size": 1,
                "created_at": "2024-01-01T00:00:00Z",
                "expires_at": None,
                "pinned": False,
            },
        ],
    }
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    manifest = repo.load(session_id)
    assert len(manifest.items) == 1
    assert str(manifest.items[0].id) == "tr_valid"


def test_list_items_filters_str_kind_format_and_pinned(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_filters")

    first_path = store.transcripts_dir(session_id) / "first.txt"
    first_path.write_text("one", encoding="utf-8")
    second_path = store.transcripts_dir(session_id) / "second.txt"
    second_path.write_text("two", encoding="utf-8")

    repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/first.txt",
        pinned=True,
        ttl_seconds=3600,
    )
    repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/second.txt",
        pinned=False,
        ttl_seconds=3600,
    )

    items = repo.list_items(session_id, kind="transcript", format="txt", pinned=True)
    assert len(items) == 1
    assert items[0].pinned is True


def test_cleanup_session_handles_invalid_missing_and_updates_size(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_cleanup")

    valid_path = store.transcripts_dir(session_id) / "valid.txt"
    valid_path.write_text("data", encoding="utf-8")

    item_empty = _make_item(item_id="tr_empty", relpath="", size=0, pinned=False, expires_at=None)
    item_invalid = _make_item(
        item_id="tr_invalid", relpath="../escape.txt", size=0, pinned=False, expires_at=None
    )
    item_missing = _make_item(
        item_id="tr_missing", relpath="transcripts/missing.txt", size=1, pinned=False, expires_at=None
    )
    item_valid = _make_item(
        item_id="tr_valid", relpath="transcripts/valid.txt", size=0, pinned=False, expires_at=None
    )

    manifest = repo.load(session_id)
    repo.save(replace(manifest, items=[item_empty, item_invalid, item_missing, item_valid]))

    removed = repo.cleanup_session(session_id)
    assert removed >= 1

    updated = repo.load(session_id)
    ids = {str(entry.id) for entry in updated.items}
    assert "tr_valid" in ids
    assert "tr_empty" not in ids
    assert "tr_invalid" not in ids
    assert "tr_missing" not in ids

    kept = updated.items[0]
    assert kept.size == len("data")
    assert kept.expires_at is not None


def test_cleanup_session_handles_unlink_error(monkeypatch, tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_unlink")

    target = store.transcripts_dir(session_id) / "expired.txt"
    target.write_text("old", encoding="utf-8")

    item = _make_item(
        item_id="tr_expired",
        relpath="transcripts/expired.txt",
        size=3,
        pinned=False,
        expires_at="2000-01-01T00:00:00Z",
    )

    manifest = repo.load(session_id)
    repo.save(replace(manifest, items=[item]))

    real_unlink = Path.unlink

    def fake_unlink(self, *args, **kwargs):
        if self == target:
            raise OSError("blocked")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    removed = repo.cleanup_session(session_id)
    assert removed == 1
    assert repo.list_items(session_id) == []


def test_cleanup_session_enforces_max_items(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600, max_session_items=1)
    session_id = SessionId("sess_limits")

    first_path = store.transcripts_dir(session_id) / "old.txt"
    first_path.write_text("old", encoding="utf-8")
    second_path = store.transcripts_dir(session_id) / "new.txt"
    second_path.write_text("new", encoding="utf-8")

    item_old = _make_item(
        item_id="tr_old",
        relpath="transcripts/old.txt",
        size=len("old"),
        pinned=False,
        expires_at=None,
    )
    item_new = _make_item(
        item_id="tr_new",
        relpath="transcripts/new.txt",
        size=len("new"),
        pinned=False,
        expires_at=None,
    )
    item_old = replace(item_old, created_at="2024-01-01T00:00:00Z")
    item_new = replace(item_new, created_at="2024-01-01T00:00:01Z")

    manifest = repo.load(session_id)
    repo.save(replace(manifest, items=[item_old, item_new]))

    removed = repo.cleanup_session(session_id)
    assert removed == 1
    remaining = repo.list_items(session_id)
    assert len(remaining) == 1
    assert str(remaining[0].id) == "tr_new"


def test_locked_file_context(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600, use_lock=True)
    session_id = SessionId("sess_lock")
    manifest = repo.load(session_id)
    repo.save(manifest)
    assert store.manifest_path(session_id).exists()


def test_parse_ts_and_sort_key():
    assert _parse_ts("not-a-date") is None
    item = _make_item(item_id="tr_sort", relpath="transcripts/a.txt", size=1, pinned=False, expires_at=None)
    key = _item_sort_key(item)
    assert isinstance(key[0], datetime)
