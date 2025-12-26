def test_add_item_and_list(server_module, unwrap):
    session_id = "sess_test"
    relpath = "transcripts/sample.txt"
    write = server_module._session_root(session_id) / relpath
    write.parent.mkdir(parents=True, exist_ok=True)
    write.write_text("hello", encoding="utf-8")

    item = server_module._add_item(
        session_id=session_id,
        kind="transcript",
        fmt="txt",
        relpath=relpath,
        pinned=False,
        ttl_seconds=3600,
    )

    listed = unwrap(server_module.list_session_items)(session_id=session_id)
    assert listed["session_id"] == session_id
    assert listed["items"]
    assert listed["items"][0]["id"] == item["id"]
    assert listed["items"][0]["relpath"] == relpath


def test_cleanup_removes_expired(server_module):
    session_id = "sess_expired"
    relpath = "transcripts/old.txt"
    target = server_module._session_root(session_id) / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")

    item = server_module._add_item(
        session_id=session_id,
        kind="transcript",
        fmt="txt",
        relpath=relpath,
        pinned=False,
        ttl_seconds=3600,
    )

    manifest = server_module._load_manifest(session_id)
    for entry in manifest["items"]:
        if entry["id"] == item["id"]:
            entry["expires_at"] = "2000-01-01T00:00:00Z"
    server_module._save_manifest(session_id, manifest)

    removed = server_module._cleanup_session(session_id)
    assert removed >= 1
    assert not target.exists()
    manifest = server_module._load_manifest(session_id)
    assert manifest["items"] == []


def test_pin_unpin_item(server_module, unwrap):
    session_id = "sess_pin"
    relpath = "transcripts/keep.txt"
    target = server_module._session_root(session_id) / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("data", encoding="utf-8")

    item = server_module._add_item(
        session_id=session_id,
        kind="transcript",
        fmt="txt",
        relpath=relpath,
        pinned=False,
        ttl_seconds=3600,
    )

    pinned = unwrap(server_module.pin_item)(item["id"], session_id=session_id)
    assert pinned["pinned"] is True
    assert pinned["expires_at"] is None

    unpinned = unwrap(server_module.unpin_item)(item["id"], session_id=session_id)
    assert unpinned["pinned"] is False
    assert unpinned["expires_at"]


def test_get_session_id_header_mismatch(server_module):
    ctx = {"mcp-session-id": "sess_ctx"}
    try:
        server_module._get_session_id(session_id="sess_other", ctx=ctx)
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("Expected mismatch error")


def test_default_session_id_fallback(server_module, monkeypatch):
    config = replace(server_module.APP_CONFIG, default_session_id="sess_default")
    monkeypatch.setattr(server_module, "APP_CONFIG", config)
    assert server_module._get_session_id() == "sess_default"
from dataclasses import replace
