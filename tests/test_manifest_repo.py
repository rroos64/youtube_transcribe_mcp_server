from dataclasses import replace
from datetime import datetime, timedelta
import os

from adapters.filesystem_store import SessionStore
from adapters.manifest_json_repo import ManifestRepository
from domain.models import ItemKind, TranscriptFormat
from domain.types import SessionId


def test_repo_add_and_list(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_repo")

    target = store.transcripts_dir(session_id) / "sample.txt"
    target.write_text("hello", encoding="utf-8")

    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/sample.txt",
        pinned=False,
        ttl_seconds=3600,
    )

    items = repo.list_items(session_id)
    assert items
    assert items[0].id == item.id
    assert items[0].relpath == "transcripts/sample.txt"


def test_repo_cleanup_removes_expired(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_expired")

    target = store.transcripts_dir(session_id) / "old.txt"
    target.write_text("old", encoding="utf-8")

    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/old.txt",
        pinned=False,
        ttl_seconds=3600,
    )

    manifest = repo.load(session_id)
    updated_items = []
    for entry in manifest.items:
        if entry.id == item.id:
            updated_items.append(replace(entry, expires_at="2000-01-01T00:00:00Z"))
        else:
            updated_items.append(entry)
    repo.save(replace(manifest, items=updated_items))

    removed = repo.cleanup_session(session_id)
    assert removed >= 1
    assert not target.exists()
    assert repo.list_items(session_id) == []


def test_repo_save_uses_atomic_replace(tmp_path, monkeypatch):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_atomic")

    manifest = repo.load(session_id)
    calls = []
    real_replace = os.replace

    def spy_replace(src, dst):
        calls.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy_replace)

    repo.save(manifest)

    assert calls
    src, dst = calls[-1]
    assert str(src).endswith(".tmp")
    assert str(dst).endswith("manifest.json")
    assert (store.manifest_path(session_id)).exists()


def test_repo_uses_clock_for_timestamps(tmp_path):
    class FixedClock:
        def __init__(self, now):
            self._now = now

        def now(self):
            return self._now

    fixed_time = datetime(2024, 1, 1, 12, 0, 0)
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=60, clock=FixedClock(fixed_time))
    session_id = SessionId("sess_clock")

    target = store.transcripts_dir(session_id) / "sample.txt"
    target.write_text("hello", encoding="utf-8")

    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/sample.txt",
        pinned=False,
        ttl_seconds=60,
    )

    expected_created = fixed_time.isoformat() + "Z"
    expected_expires = (fixed_time + timedelta(seconds=60)).isoformat() + "Z"
    assert item.created_at == expected_created
    assert item.expires_at == expected_expires
