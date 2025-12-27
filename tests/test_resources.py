import json
from dataclasses import replace

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.config import AppConfig
from yt_dlp_transcriber.domain.models import ItemKind, TranscriptFormat
from yt_dlp_transcriber.domain.time_utils import parse_iso_timestamp
from yt_dlp_transcriber.domain.types import SessionId
from yt_dlp_transcriber.mcp.deps import build_services, set_services
from yt_dlp_transcriber.mcp.resources import resource_session_item, resource_session_latest
from yt_dlp_transcriber.mcp.templates import template_summary
from yt_dlp_transcriber.services.session_service import SessionService


def _make_services(tmp_path):
    config = AppConfig.from_env({"DATA_DIR": str(tmp_path)})
    return build_services(config)


def test_read_file_info_and_chunk(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)
    session_id = SessionId("sess_read")

    target = store.transcripts_dir(session_id) / "read.txt"
    target.write_text("hello world", encoding="utf-8")
    item = repo.add_item(
        session_id=session_id,
        kind=ItemKind.TRANSCRIPT,
        fmt=TranscriptFormat.TXT,
        relpath="transcripts/read.txt",
        pinned=False,
        ttl_seconds=3600,
    )

    info = service.read_file_info(item_id=item.id, session_id=session_id)
    assert info.id == item.id
    assert info.size == len("hello world")
    assert info.relpath.startswith("transcripts/")

    chunk = service.read_file_chunk(
        item_id=item.id, session_id=session_id, offset=0, max_bytes=5
    )
    assert chunk.data == "hello"
    assert chunk.eof is False
    assert chunk.id == item.id


def test_resource_session_item_inline(tmp_path):
    services = _make_services(tmp_path)
    set_services(services)
    try:
        store = services.store
        repo = services.manifest_repo
        session_id = SessionId("sess_resource")
        relpath = "transcripts/inline.txt"
        target = store.transcripts_dir(session_id) / "inline.txt"
        target.write_text("inline", encoding="utf-8")
        item = repo.add_item(
            session_id=session_id,
            kind=ItemKind.TRANSCRIPT,
            fmt=TranscriptFormat.TXT,
            relpath=relpath,
            pinned=False,
            ttl_seconds=3600,
        )

        payload = resource_session_item(str(session_id), str(item.id))
        data = json.loads(payload)
        assert data["session_id"] == str(session_id)
        assert data["item"]["id"] == str(item.id)
        assert data["content"] == "inline"
        assert data["truncated"] is False
    finally:
        set_services(None)


def test_template_summary_includes_session():
    ctx = {"mcp-session-id": "sess_template"}
    payload = template_summary("tr_abc123", ctx=ctx)
    data = json.loads(payload)
    assert data["inputs"]["session_id"] == "sess_template"
    assert "transcripts://session/sess_template/item/tr_abc123" in data["recommended_steps"][0]


def test_resource_session_item_truncates_large_content(tmp_path):
    config = AppConfig.from_env(
        {"DATA_DIR": str(tmp_path), "INLINE_TEXT_MAX_BYTES": "1"}
    )
    services = build_services(config)
    set_services(services)
    try:
        store = services.store
        repo = services.manifest_repo
        session_id = SessionId("sess_truncate")
        relpath = "transcripts/large.txt"
        target = store.transcripts_dir(session_id) / "large.txt"
        target.write_text("longer text", encoding="utf-8")
        item = repo.add_item(
            session_id=session_id,
            kind=ItemKind.TRANSCRIPT,
            fmt=TranscriptFormat.TXT,
            relpath=relpath,
            pinned=False,
            ttl_seconds=3600,
        )

        payload = resource_session_item(str(session_id), str(item.id))
        data = json.loads(payload)
        assert data["content"] is None
        assert data["truncated"] is True
    finally:
        set_services(None)


def test_resource_session_latest_returns_newest_item(tmp_path):
    services = _make_services(tmp_path)
    set_services(services)
    try:
        store = services.store
        repo = services.manifest_repo
        session_id = SessionId("sess_latest")
        first_path = store.transcripts_dir(session_id) / "first.txt"
        first_path.write_text("first", encoding="utf-8")
        second_path = store.transcripts_dir(session_id) / "second.txt"
        second_path.write_text("second", encoding="utf-8")

        first = repo.add_item(
            session_id=session_id,
            kind=ItemKind.TRANSCRIPT,
            fmt=TranscriptFormat.TXT,
            relpath="transcripts/first.txt",
            pinned=False,
            ttl_seconds=3600,
        )
        second = repo.add_item(
            session_id=session_id,
            kind=ItemKind.TRANSCRIPT,
            fmt=TranscriptFormat.TXT,
            relpath="transcripts/second.txt",
            pinned=False,
            ttl_seconds=3600,
        )

        manifest = repo.load(session_id)
        updated_items = []
        for entry in manifest.items:
            if entry.id == first.id:
                updated_items.append(replace(entry, created_at="2024-01-01T00:00:00Z"))
            elif entry.id == second.id:
                updated_items.append(replace(entry, created_at="2024-01-01T00:00:01Z"))
            else:
                updated_items.append(entry)
        repo.save(replace(manifest, items=updated_items))

        payload = resource_session_latest(str(session_id))
        data = json.loads(payload)
        assert data["item"]["id"] == str(second.id)
    finally:
        set_services(None)


def test_parse_ts_returns_none_on_invalid():
    assert parse_iso_timestamp("not-a-date") is None
