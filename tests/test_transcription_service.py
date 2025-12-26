from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.manifest_json_repo import ManifestRepository
from yt_dlp_transcriber.adapters.ytdlp_client import YtDlpSubtitles
from yt_dlp_transcriber.domain.models import ItemKind, TranscriptFormat
from yt_dlp_transcriber.domain.types import SessionId
from yt_dlp_transcriber.services.transcription_service import TranscriptParser, TranscriptionService


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
