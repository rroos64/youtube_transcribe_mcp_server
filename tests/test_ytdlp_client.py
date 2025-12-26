from subprocess import CompletedProcess

import pytest

from yt_dlp_transcriber.adapters.ytdlp_client import YtDlpClient
from yt_dlp_transcriber.config import AppConfig
from yt_dlp_transcriber.domain.errors import ExternalCommandError


def test_ytdlp_client_get_info_parses_json():
    env = {
        "YTDLP_BIN": "/bin/yt-dlp",
        "YTDLP_REMOTE_EJS": "ejs:test",
        "YTDLP_PLAYER_CLIENT": "web",
        "YTDLP_TIMEOUT_SEC": "5",
    }
    config = AppConfig.from_env(env)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return CompletedProcess(
            cmd,
            0,
            stdout='line1\n{"duration": 10, "title": "t"}\n',
        )

    client = YtDlpClient(config, runner=fake_run)
    info = client.get_info("https://youtube.com/watch?v=abc")

    assert info["duration"] == 10
    assert captured["cmd"][0] == "/bin/yt-dlp"
    assert "ejs:test" in captured["cmd"]
    assert "youtube:player_client=web" in captured["cmd"]


def test_ytdlp_client_raises_on_failure():
    config = AppConfig.from_env({"YTDLP_TIMEOUT_SEC": "5"})

    def fake_run(cmd, **kwargs):
        return CompletedProcess(cmd, 1, stdout="boom")

    client = YtDlpClient(config, runner=fake_run)

    with pytest.raises(ExternalCommandError):
        client.get_info("https://youtube.com/watch?v=abc")


def test_ytdlp_client_info_cache_respects_ttl():
    config = AppConfig.from_env({"YTDLP_TIMEOUT_SEC": "5"})
    calls = {"count": 0}
    clock = {"now": 1000.0}

    def fake_time():
        return clock["now"]

    def fake_run(cmd, **kwargs):
        calls["count"] += 1
        return CompletedProcess(
            cmd,
            0,
            stdout='{"duration": 10, "title": "cached"}\n',
        )

    client = YtDlpClient(config, runner=fake_run, cache_ttl_sec=60, time_provider=fake_time)

    first = client.get_info("https://youtube.com/watch?v=abc")
    second = client.get_info("https://youtube.com/watch?v=abc")

    assert first["title"] == "cached"
    assert second["title"] == "cached"
    assert calls["count"] == 1

    clock["now"] += 61
    client.get_info("https://youtube.com/watch?v=abc")
    assert calls["count"] == 2
