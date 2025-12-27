from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AppConfig:
    ytdlp_bin: str
    player_client: str
    remote_ejs: str
    sub_lang: str
    timeout_sec: int
    auto_text_max_bytes: int
    default_ttl_sec: int
    inline_text_max_bytes: int
    info_cache_ttl_sec: int
    max_session_items: int
    max_session_bytes: int
    default_session_id: str
    data_dir: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AppConfig":
        if env is None:
            env = os.environ

        default_ttl_raw = env.get("TRANSCRIPT_TTL_SECONDS") or env.get("DEFAULT_TTL_SEC") or "3600"

        return cls(
            ytdlp_bin=env.get("YTDLP_BIN", "yt-dlp"),
            player_client=env.get("YTDLP_PLAYER_CLIENT", "web_safari"),
            remote_ejs=env.get("YTDLP_REMOTE_EJS", "ejs:github"),
            sub_lang=env.get("YTDLP_SUB_LANG", "en.*"),
            timeout_sec=int(env.get("YTDLP_TIMEOUT_SEC", "180")),
            auto_text_max_bytes=int(env.get("AUTO_TEXT_MAX_BYTES", "200000")),
            default_ttl_sec=int(default_ttl_raw),
            inline_text_max_bytes=int(env.get("INLINE_TEXT_MAX_BYTES", "20000")),
            info_cache_ttl_sec=int(env.get("YTDLP_INFO_CACHE_TTL_SEC", "300")),
            max_session_items=int(env.get("MAX_SESSION_ITEMS", "0")),
            max_session_bytes=int(env.get("MAX_SESSION_BYTES", "0")),
            default_session_id=env.get("DEFAULT_SESSION_ID", ""),
            data_dir=Path(env.get("DATA_DIR", "/data")),
        )
