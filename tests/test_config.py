from pathlib import Path

from yt_dlp_transcriber.config import AppConfig


def test_config_defaults():
    config = AppConfig.from_env({})

    assert config.ytdlp_bin == "yt-dlp"
    assert config.player_client == "web_safari"
    assert config.remote_ejs == "ejs:github"
    assert config.sub_lang == "en.*"
    assert config.timeout_sec == 180
    assert config.auto_text_max_bytes == 200000
    assert config.default_ttl_sec == 3600
    assert config.inline_text_max_bytes == 20000
    assert config.info_cache_ttl_sec == 300
    assert config.max_session_items == 0
    assert config.max_session_bytes == 0
    assert config.default_session_id == ""
    assert config.data_dir == Path("/data")


def test_config_env_overrides():
    env = {
        "YTDLP_BIN": "/bin/yt-dlp",
        "YTDLP_PLAYER_CLIENT": "web",
        "YTDLP_REMOTE_EJS": "ejs:local",
        "YTDLP_SUB_LANG": "en",
        "YTDLP_TIMEOUT_SEC": "42",
        "AUTO_TEXT_MAX_BYTES": "123",
        "TRANSCRIPT_TTL_SECONDS": "555",
        "DEFAULT_TTL_SEC": "222",
        "INLINE_TEXT_MAX_BYTES": "321",
        "YTDLP_INFO_CACHE_TTL_SEC": "600",
        "MAX_SESSION_ITEMS": "10",
        "MAX_SESSION_BYTES": "4096",
        "DEFAULT_SESSION_ID": "sess_default",
        "DATA_DIR": "/tmp/data",
    }
    config = AppConfig.from_env(env)

    assert config.ytdlp_bin == "/bin/yt-dlp"
    assert config.player_client == "web"
    assert config.remote_ejs == "ejs:local"
    assert config.sub_lang == "en"
    assert config.timeout_sec == 42
    assert config.auto_text_max_bytes == 123
    assert config.default_ttl_sec == 555
    assert config.inline_text_max_bytes == 321
    assert config.info_cache_ttl_sec == 600
    assert config.max_session_items == 10
    assert config.max_session_bytes == 4096
    assert config.default_session_id == "sess_default"
    assert config.data_dir == Path("/tmp/data")


def test_config_default_ttl_fallback():
    config = AppConfig.from_env({"DEFAULT_TTL_SEC": "7200"})
    assert config.default_ttl_sec == 7200
