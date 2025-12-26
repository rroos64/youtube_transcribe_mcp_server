import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_dlp_transcriber.config import AppConfig
import yt_dlp_transcriber.server as server


@pytest.fixture()
def server_module(tmp_path, monkeypatch):
    config = AppConfig.from_env(
        {
            "DATA_DIR": str(tmp_path),
            "INLINE_TEXT_MAX_BYTES": "20000",
            "DEFAULT_TTL_SEC": "3600",
            "MAX_SESSION_ITEMS": "0",
            "MAX_SESSION_BYTES": "0",
            "DEFAULT_SESSION_ID": "",
        }
    )
    monkeypatch.setattr(server, "APP_CONFIG", config)
    return server


def unwrap_callable(obj):
    if callable(obj):
        return obj
    for attr in ("fn", "func", "function", "_func", "_fn", "__wrapped__"):
        candidate = getattr(obj, attr, None)
        if callable(candidate):
            return candidate
    raise TypeError(f"Unable to unwrap callable for {type(obj)}")


@pytest.fixture()
def unwrap():
    return unwrap_callable
