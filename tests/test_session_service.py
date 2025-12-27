import pytest

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.domain.errors import NotFoundError
from yt_dlp_transcriber.domain.models import ItemKind, TranscriptFormat
from yt_dlp_transcriber.domain.types import SessionId
from yt_dlp_transcriber.services.session_service import SessionService


def test_set_item_ttl_rejects_non_positive(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_ttl")

    with pytest.raises(ValueError):
        service.set_item_ttl("tr_ttl", 0, session_id=session_id)


def test_delete_item_removes_file_and_manifest(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_delete")

    target = store.transcripts_dir(session_id) / "delete.txt"
    target.write_text("data", encoding="utf-8")

    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/delete.txt",
        pinned=False,
        ttl_seconds=3600,
    )

    assert service.delete_item(item.id, session_id=session_id) is True
    assert not target.exists()
    assert repo.list_items(session_id) == []


def test_write_text_file_validates_relpath_and_overwrite(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_write")

    with pytest.raises(ValueError):
        service.write_text_file(relpath="", content="x", session_id=session_id)

    with pytest.raises(ValueError):
        service.write_text_file(relpath="../bad.txt", content="x", session_id=session_id)

    service.write_text_file(relpath="note.txt", content="x", session_id=session_id)
    with pytest.raises(ValueError):
        service.write_text_file(relpath="note.txt", content="x", session_id=session_id)


def test_read_file_info_by_relpath(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_info")

    target = store.transcripts_dir(session_id) / "manual.txt"
    target.write_text("hello", encoding="utf-8")

    info = service.read_file_info(session_id=session_id, relpath="transcripts/manual.txt")
    assert info.id is None
    assert info.relpath == "transcripts/manual.txt"
    assert info.size == len("hello")


def test_read_file_chunk_validation_and_not_found(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_chunk")

    with pytest.raises(ValueError):
        service.read_file_chunk(session_id=session_id, relpath="transcripts/a.txt", max_bytes=0)

    with pytest.raises(ValueError):
        service.read_file_chunk(session_id=session_id, relpath="transcripts/a.txt", offset=-1)

    with pytest.raises(NotFoundError):
        service.read_file_chunk(session_id=session_id, item_id="tr_missing")


def test_read_file_chunk_eof_when_offset_past_size(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_eof")

    target = store.transcripts_dir(session_id) / "small.txt"
    target.write_text("data", encoding="utf-8")

    chunk = service.read_file_chunk(
        session_id=session_id,
        relpath="transcripts/small.txt",
        offset=10,
        max_bytes=5,
    )
    assert chunk.eof is True
    assert chunk.data == ""


def test_update_item_handles_missing_and_other_items(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_update")

    first_path = store.transcripts_dir(session_id) / "first.txt"
    first_path.write_text("one", encoding="utf-8")
    second_path = store.transcripts_dir(session_id) / "second.txt"
    second_path.write_text("two", encoding="utf-8")

    first = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/first.txt",
        pinned=False,
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

    pinned = service.pin_item(first.id, session_id=session_id)
    assert pinned.pinned is True

    with pytest.raises(NotFoundError):
        service.pin_item("tr_missing", session_id=session_id)
