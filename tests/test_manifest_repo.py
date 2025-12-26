from dataclasses import replace

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.domain.models import ItemKind, TranscriptFormat
from yt_dlp_transcriber.domain.types import SessionId


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
