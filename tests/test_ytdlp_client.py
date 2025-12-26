from subprocess import CompletedProcess

from yt_dlp_transcriber.adapters.ytdlp_client import YtDlpClient
from yt_dlp_transcriber.config import AppConfig


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
