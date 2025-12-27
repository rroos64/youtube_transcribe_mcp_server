from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain.models import ItemKind, ManifestItem, TranscriptFormat
from domain.types import ItemId, SessionId
from services.session_service import FileChunk, FileInfo
from services.transcription_service import TranscriptionResult, VideoInfo
import mcp_server.tools as tools


@dataclass
class FakeConfig:
    default_session_id: str = ""
    auto_text_max_bytes: int = 200000


class FakeTranscriptionService:
    def __init__(self, *, text: str, item: ManifestItem, auto_result: TranscriptionResult) -> None:
        self.text = text
        self.item = item
        self.auto_result = auto_result
        self.calls: list[tuple] = []

    def transcribe_to_text(self, url: str) -> str:
        self.calls.append(("text", url))
        return self.text

    def transcribe_to_file(self, *, url: str, fmt: TranscriptFormat, session_id: SessionId | str) -> ManifestItem:
        self.calls.append(("file", url, fmt, session_id))
        return self.item

    def transcribe_auto(
        self,
        *,
        url: str,
        fmt: TranscriptFormat,
        max_text_bytes: int,
        session_id: SessionId | str | None,
    ) -> TranscriptionResult:
        self.calls.append(("auto", url, fmt, max_text_bytes, session_id))
        return self.auto_result


class FakeYtdlpClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def get_info(self, url: str) -> dict:
        self.calls.append(url)
        return self.payload


class FakeSessionService:
    def __init__(self, *, item: ManifestItem, info: FileInfo, chunk: FileChunk) -> None:
        self.item = item
        self.info = info
        self.chunk = chunk
        self.calls: list[tuple] = []

    def list_items(self, session_id, *, kind=None, format=None, pinned=None):
        self.calls.append(("list", session_id, kind, format, pinned))
        return [self.item]

    def pin_item(self, item_id, *, session_id):
        self.calls.append(("pin", item_id, session_id))
        return self.item

    def unpin_item(self, item_id, *, session_id):
        self.calls.append(("unpin", item_id, session_id))
        return self.item

    def set_item_ttl(self, item_id, ttl_seconds, *, session_id):
        self.calls.append(("ttl", item_id, ttl_seconds, session_id))
        return self.item

    def delete_item(self, item_id, *, session_id):
        self.calls.append(("delete", item_id, session_id))
        return True

    def write_text_file(self, *, relpath, content, overwrite, session_id):
        self.calls.append(("write", relpath, overwrite, session_id))
        return self.item

    def read_file_info(self, *, session_id, item_id, relpath):
        self.calls.append(("info", session_id, item_id, relpath))
        return self.info

    def read_file_chunk(self, *, session_id, offset, max_bytes, item_id, relpath):
        self.calls.append(("chunk", session_id, offset, max_bytes, item_id, relpath))
        return self.chunk


def _make_item() -> ManifestItem:
    return ManifestItem(
        id=ItemId("item-1"),
        kind=ItemKind.TRANSCRIPT,
        format=TranscriptFormat.TXT,
        relpath="transcripts/sample.txt",
        size=12,
        created_at="2024-01-01T00:00:00Z",
        expires_at=None,
        pinned=False,
    )


def _make_services(*, auto_result: TranscriptionResult | None = None):
    item = _make_item()
    info = FileInfo(
        id=item.id,
        session_id=SessionId("session-1"),
        path=Path("/tmp/path.txt"),
        relpath=item.relpath,
        size=item.size,
        pinned=item.pinned,
        expires_at=item.expires_at,
        format=item.format,
        kind=item.kind,
    )
    chunk = FileChunk(
        data="chunk",
        next_offset=5,
        eof=True,
        size=item.size,
        path=Path("/tmp/path.txt"),
        id=item.id,
    )
    if auto_result is None:
        auto_result = TranscriptionResult(
            kind="text",
            text="auto",
            item=None,
            bytes=4,
            info=VideoInfo(duration=None, duration_string=None, title=None, is_live=None),
        )
    return SimpleNamespace(
        config=FakeConfig(),
        transcription_service=FakeTranscriptionService(text="plain", item=item, auto_result=auto_result),
        session_service=FakeSessionService(item=item, info=info, chunk=chunk),
        ytdlp_client=FakeYtdlpClient(
            {
                "duration": 12,
                "duration_string": "0:12",
                "title": "Demo",
                "is_live": False,
            }
        ),
    )


def test_youtube_transcribe_rejects_invalid_url():
    with pytest.raises(ValueError, match="Please provide a valid YouTube video URL"):
        tools.youtube_transcribe("https://example.com/video")


def test_youtube_transcribe_uses_service(monkeypatch):
    services = _make_services()
    monkeypatch.setattr(tools, "get_services", lambda: services)

    text = tools.youtube_transcribe("https://youtu.be/demo")

    assert text == "plain"
    assert ("text", "https://youtu.be/demo") in services.transcription_service.calls


def test_youtube_transcribe_to_file_rejects_invalid_format():
    with pytest.raises(ValueError, match="fmt must be one of"):
        tools.youtube_transcribe_to_file("https://youtu.be/demo", fmt="doc", session_id="session-1")


def test_youtube_transcribe_to_file_returns_payload(monkeypatch):
    services = _make_services()
    monkeypatch.setattr(tools, "get_services", lambda: services)

    payload = tools.youtube_transcribe_to_file("https://youtu.be/demo", session_id="session-1")

    assert payload["session_id"] == "session-1"
    assert payload["id"] == "item-1"
    assert payload["kind"] == ItemKind.TRANSCRIPT.value


def test_youtube_get_duration_payload(monkeypatch):
    services = _make_services()
    monkeypatch.setattr(tools, "get_services", lambda: services)

    payload = tools.youtube_get_duration("https://youtu.be/demo")

    assert payload["duration"] == 12
    assert payload["duration_string"] == "0:12"
    assert payload["title"] == "Demo"
    assert payload["is_live"] is False


def test_youtube_transcribe_auto_returns_text(monkeypatch):
    services = _make_services()
    monkeypatch.setattr(tools, "get_services", lambda: services)

    payload = tools.youtube_transcribe_auto("https://youtu.be/demo")

    assert payload["kind"] == "text"
    assert payload["text"] == "auto"
    assert payload["bytes"] == 4


def test_youtube_transcribe_auto_requires_session_for_file(monkeypatch):
    item = _make_item()
    auto_result = TranscriptionResult(
        kind="file",
        text=None,
        item=item,
        bytes=2000,
        info=VideoInfo(duration=None, duration_string=None, title=None, is_live=None),
    )
    services = _make_services(auto_result=auto_result)
    monkeypatch.setattr(tools, "get_services", lambda: services)
    monkeypatch.setattr(tools, "get_session_id", lambda **_kwargs: None)

    with pytest.raises(ValueError, match="session_id is required"):
        tools.youtube_transcribe_auto("https://youtu.be/demo")


def test_session_management_tools(monkeypatch):
    services = _make_services()
    monkeypatch.setattr(tools, "get_services", lambda: services)

    payload = tools.list_session_items(session_id="session-1")
    assert payload["session_id"] == "session-1"
    assert payload["items"][0]["id"] == "item-1"

    assert tools.pin_item("item-1", session_id="session-1")["id"] == "item-1"
    assert tools.unpin_item("item-1", session_id="session-1")["id"] == "item-1"
    assert tools.set_item_ttl("item-1", 10, session_id="session-1")["id"] == "item-1"
    assert tools.delete_item("item-1", session_id="session-1")["deleted"] is True


def test_file_tools(monkeypatch):
    services = _make_services()
    monkeypatch.setattr(tools, "get_services", lambda: services)

    payload = tools.write_text_file("notes.txt", "hi", session_id="session-1")
    assert payload["session_id"] == "session-1"
    assert payload["id"] == "item-1"

    info = tools.read_file_info(session_id="session-1", item_id="item-1")
    assert info["id"] == "item-1"
    assert info["relpath"] == "transcripts/sample.txt"

    chunk = tools.read_file_chunk(session_id="session-1", item_id="item-1")
    assert chunk["data"] == "chunk"
    assert chunk["eof"] is True
