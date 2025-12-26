from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yt_dlp_transcriber.domain.types import SessionId

_TRANSCRIPTS_DIR = "transcripts"
_DERIVED_DIR = "derived"
_MANIFEST_NAME = "manifest.json"


def _coerce_session_id(session_id: SessionId | str) -> SessionId:
    if isinstance(session_id, SessionId):
        return session_id
    return SessionId(str(session_id))


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class SessionStore:
    data_dir: Path

    def __init__(self, data_dir: Path | str) -> None:
        object.__setattr__(self, "data_dir", Path(data_dir))

    def session_root(self, session_id: SessionId | str) -> Path:
        sid = _coerce_session_id(session_id)
        root = self.data_dir / str(sid)
        root.mkdir(parents=True, exist_ok=True)
        (root / _TRANSCRIPTS_DIR).mkdir(parents=True, exist_ok=True)
        (root / _DERIVED_DIR).mkdir(parents=True, exist_ok=True)
        return root

    def transcripts_dir(self, session_id: SessionId | str) -> Path:
        return self.session_root(session_id) / _TRANSCRIPTS_DIR

    def derived_dir(self, session_id: SessionId | str) -> Path:
        return self.session_root(session_id) / _DERIVED_DIR

    def manifest_path(self, session_id: SessionId | str) -> Path:
        return self.session_root(session_id) / _MANIFEST_NAME

    def resolve_relpath(self, session_id: SessionId | str, relpath: str) -> Path:
        if not relpath or relpath.startswith("/") or ".." in relpath.split("/"):
            raise ValueError("relpath must be a safe relative path")

        root = self.session_root(session_id)
        path = (root / relpath).resolve()
        if not _is_within_root(path, root):
            raise ValueError("relpath resolves outside session directory")
        return path
