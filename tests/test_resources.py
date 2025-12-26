import json

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.config import AppConfig
from yt_dlp_transcriber.domain.models import ItemKind, TranscriptFormat
from yt_dlp_transcriber.domain.types import SessionId
from yt_dlp_transcriber.mcp.deps import build_services, set_services
from yt_dlp_transcriber.mcp.resources import resource_session_item
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
