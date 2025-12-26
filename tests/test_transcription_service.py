from yt_dlp_transcriber.adapters.filesystem_store import SessionStore
from yt_dlp_transcriber.adapters.ytdlp_client import YtDlpSubtitles
from yt_dlp_transcriber.domain.models import TranscriptFormat
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
    service = TranscriptionService(client, TranscriptParser(), store)

    result = service.transcribe_auto(
        url="https://youtube.com/watch?v=abc",
        fmt=TranscriptFormat.TXT,
        max_text_bytes=100,
        session_id=SessionId("sess_auto"),
    )

    assert result.kind == "text"
    assert result.text == "Hello world"
    assert result.path is None


def test_transcribe_auto_returns_file_when_large(tmp_path):
    vtt_text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello world\n"
    client = FakeYtDlpClient(vtt_text)
    store = SessionStore(tmp_path)
    service = TranscriptionService(client, TranscriptParser(), store)

    result = service.transcribe_auto(
        url="https://youtube.com/watch?v=abc",
        fmt=TranscriptFormat.TXT,
        max_text_bytes=1,
        session_id=SessionId("sess_auto"),
    )

    assert result.kind == "file"
    assert result.path is not None
    assert result.path.exists()
    assert result.path.suffix == ".txt"
    assert result.path.read_text(encoding="utf-8") == "Hello world\n"
