from dataclasses import replace

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.domain.models import ItemKind, TranscriptFormat
from yt_dlp_transcriber.domain.types import SessionId
from yt_dlp_transcriber.mcp.session import get_session_id
from yt_dlp_transcriber.services.session_service import SessionService


def test_add_item_and_list(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_test")
    relpath = "transcripts/sample.txt"
    write = store.transcripts_dir(session_id) / "sample.txt"
    write.write_text("hello", encoding="utf-8")

    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath=relpath,
        pinned=False,
        ttl_seconds=3600,
    )

    listed = service.list_items(session_id)
    assert listed
    assert listed[0].id == item.id
    assert listed[0].relpath == relpath


def test_cleanup_removes_expired(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    session_id = SessionId("sess_expired")
    relpath = "transcripts/old.txt"
    target = store.transcripts_dir(session_id) / "old.txt"
    target.write_text("old", encoding="utf-8")

    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath=relpath,
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


def test_pin_unpin_item(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_pin")
    relpath = "transcripts/keep.txt"
    target = store.transcripts_dir(session_id) / "keep.txt"
    target.write_text("data", encoding="utf-8")

    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath=relpath,
        pinned=False,
        ttl_seconds=3600,
    )

    pinned = service.pin_item(item.id, session_id=session_id)
    assert pinned.pinned is True
    assert pinned.expires_at is None

    unpinned = service.unpin_item(item.id, session_id=session_id)
    assert unpinned.pinned is False
    assert unpinned.expires_at


def test_get_session_id_header_mismatch():
    ctx = {"mcp-session-id": "sess_ctx"}
    try:
        get_session_id(session_id="sess_other", ctx=ctx, default_session_id="")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("Expected mismatch error")


def test_default_session_id_fallback():
    assert str(get_session_id(default_session_id="sess_default")) == "sess_default"
from dataclasses import replace
