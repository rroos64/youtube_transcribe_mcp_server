import pytest

from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.adapters.ytdlp_client import YtDlpSubtitles
from yt_dlp_transcriber.domain.models import ItemKind, TranscriptFormat
from yt_dlp_transcriber.domain.types import SessionId
from yt_dlp_transcriber.services.transcription_service import (
    JsonlWriter,
    TranscriptParser,
    TranscriptionService,
    VttWriter,
)


class FakeYtDlpClient:
    def __init__(self, vtt_text: str, info: dict | None = None) -> None:
        self._vtt_text = vtt_text
        self._info = info or {}

    def get_info(self, url: str) -> dict:
        return self._info

    def get_subtitles(self, url: str) -> YtDlpSubtitles:
        return YtDlpSubtitles(vtt_text=self._vtt_text, stdout="", picked_file="test.vtt")


def test_transcribe_auto_returns_text_when_small(tmp_path):
    vtt_text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello world\n"
    client = FakeYtDlpClient(vtt_text)
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = TranscriptionService(client, TranscriptParser(), store, repo)
    session_id = SessionId("sess_auto")

    result = service.transcribe_auto(
        url="https://youtube.com/watch?v=abc",
        fmt=TranscriptFormat.TXT,
        max_text_bytes=100,
        session_id=session_id,
    )

    assert result.kind == "text"
    assert result.text == "Hello world"
    assert result.item is None


def test_transcribe_auto_returns_file_when_large(tmp_path):
    vtt_text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello world\n"
    client = FakeYtDlpClient(vtt_text)
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = TranscriptionService(client, TranscriptParser(), store, repo)
    session_id = SessionId("sess_auto")

    result = service.transcribe_auto(
        url="https://youtube.com/watch?v=abc",
        fmt=TranscriptFormat.TXT,
        max_text_bytes=1,
        session_id=session_id,
    )

    assert result.kind == "file"
    assert result.text is None
    assert result.item is not None
    assert result.item.kind is ItemKind.TRANSCRIPT
    assert result.item.format == TranscriptFormat.TXT.value

    path = store.resolve_relpath(session_id, result.item.relpath)
    assert path.exists()
    assert path.suffix == ".txt"
    assert path.read_text(encoding="utf-8") == "Hello world\n"


def test_transcript_parser_dedupe_and_windowing():
    parser = TranscriptParser()
    lines = ["hello", "hello", "world", "hello"]
    deduped = parser.dedupe_lines(lines, window=2)
    assert deduped == ["hello", "world"]

    windowed = parser.dedupe_lines(["a", "b", "c"], window=1)
    assert windowed == ["a", "b", "c"]


def test_transcribe_to_text_raises_on_empty(tmp_path):
    client = FakeYtDlpClient("WEBVTT\n\n")
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = TranscriptionService(client, TranscriptParser(), store, repo)

    with pytest.raises(RuntimeError):
        service.transcribe_to_text("https://youtube.com/watch?v=abc")


def test_transcribe_to_file_raises_on_empty(tmp_path):
    client = FakeYtDlpClient("WEBVTT\n\n")
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = TranscriptionService(client, TranscriptParser(), store, repo)
    session_id = SessionId("sess_empty")

    with pytest.raises(RuntimeError):
        service.transcribe_to_file(
            url="https://youtube.com/watch?v=abc",
            fmt=TranscriptFormat.TXT,
            session_id=session_id,
        )


def test_transcribe_auto_validates_inputs(tmp_path):
    client = FakeYtDlpClient("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n")
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = TranscriptionService(client, TranscriptParser(), store, repo)

    with pytest.raises(ValueError):
        service.transcribe_auto(
            url="https://youtube.com/watch?v=abc",
            fmt=TranscriptFormat.TXT,
            max_text_bytes=0,
            session_id=SessionId("sess_auto"),
        )

    with pytest.raises(ValueError):
        service.transcribe_auto(
            url="https://youtube.com/watch?v=abc",
            fmt=TranscriptFormat.TXT,
            max_text_bytes=1,
            session_id=None,
        )


def test_transcribe_to_file_requires_writer(tmp_path):
    client = FakeYtDlpClient("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n")
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = TranscriptionService(
        client,
        TranscriptParser(),
        store,
        repo,
        writers={TranscriptFormat.VTT: VttWriter()},
    )
    session_id = SessionId("sess_writer")

    with pytest.raises(ValueError):
        service.transcribe_to_file(
            url="https://youtube.com/watch?v=abc",
            fmt=TranscriptFormat.TXT,
            session_id=session_id,
        )


def test_writers_create_files(tmp_path):
    base = tmp_path / "out"
    transcript = "line1\nline2"
    vtt_text = "WEBVTT\n\nHello"

    vtt_path = VttWriter().write(base, transcript, vtt_text)
    assert vtt_path.suffix == ".vtt"
    assert vtt_path.read_text(encoding="utf-8") == vtt_text

    jsonl_path = JsonlWriter().write(base, transcript, vtt_text)
    assert jsonl_path.suffix == ".jsonl"
    assert jsonl_path.read_text(encoding="utf-8").splitlines() == [
        '{"text": "line1"}',
        '{"text": "line2"}',
    ]
