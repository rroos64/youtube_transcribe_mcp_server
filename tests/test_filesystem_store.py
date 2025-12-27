import pytest

from adapters.filesystem_store import SessionStore
from domain.types import SessionId


def test_session_store_creates_dirs(tmp_path):
    store = SessionStore(tmp_path)
    session_id = SessionId("sess_dirs")

    root = store.session_root(session_id)
    assert root.exists()
    assert (root / "transcripts").is_dir()
    assert (root / "derived").is_dir()


def test_session_store_accepts_string_session_id(tmp_path):
    store = SessionStore(tmp_path)
    root = store.session_root("sess_str")
    assert root.exists()


def test_resolve_relpath_rejects_traversal(tmp_path):
    store = SessionStore(tmp_path)
    session_id = SessionId("sess_safe")

    with pytest.raises(ValueError):
        store.resolve_relpath(session_id, "../outside.txt")

    with pytest.raises(ValueError):
        store.resolve_relpath(session_id, "/abs/path.txt")


def test_resolve_relpath_within_root(tmp_path):
    store = SessionStore(tmp_path)
    session_id = SessionId("sess_safe")

    path = store.resolve_relpath(session_id, "transcripts/sample.txt")
    assert path.parent == store.transcripts_dir(session_id)


def test_resolve_relpath_rejects_symlink_escape(tmp_path):
    store = SessionStore(tmp_path)
    session_id = SessionId("sess_link")
    root = store.session_root(session_id)

    outside = tmp_path / "outside.txt"
    outside.write_text("data", encoding="utf-8")

    link = root / "transcripts" / "escape"
    link.symlink_to(outside)

    with pytest.raises(ValueError):
        store.resolve_relpath(session_id, "transcripts/escape")
