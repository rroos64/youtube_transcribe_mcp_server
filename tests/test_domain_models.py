import pytest

from yt_dlp_transcriber.domain.models import ItemKind, Manifest, ManifestItem, TranscriptFormat
from yt_dlp_transcriber.domain.types import ItemId, SessionId, _validate_id


def test_session_id_validation():
    assert str(SessionId("sess_123")) == "sess_123"

    with pytest.raises(ValueError):
        SessionId("")

    with pytest.raises(ValueError):
        SessionId("bad id")

    with pytest.raises(ValueError):
        SessionId("x" * 65)


def test_item_id_validation():
    assert str(ItemId("tr_abc123")) == "tr_abc123"

    with pytest.raises(ValueError):
        ItemId("")

    with pytest.raises(ValueError):
        ItemId("bad id")


def test_validate_id_unknown_name_raises():
    with pytest.raises(ValueError):
        _validate_id("", "other")


def test_manifest_item_round_trip():
    item = ManifestItem(
        id=ItemId("tr_abc123"),
        kind=ItemKind.TRANSCRIPT,
        format=TranscriptFormat.TXT,
        relpath="transcripts/sample.txt",
        size=5,
        created_at="2024-01-01T00:00:00Z",
        expires_at=None,
        pinned=False,
    )

    payload = item.to_dict()
    assert payload["id"] == "tr_abc123"
    assert payload["kind"] == "transcript"
    assert payload["format"] == "txt"

    parsed = ManifestItem.from_dict(payload)
    assert parsed.id == ItemId("tr_abc123")
    assert parsed.kind is ItemKind.TRANSCRIPT
    assert parsed.format == TranscriptFormat.TXT.value


def test_manifest_round_trip():
    item = ManifestItem(
        id=ItemId("tr_abc123"),
        kind=ItemKind.TRANSCRIPT,
        format=TranscriptFormat.TXT,
        relpath="transcripts/sample.txt",
        size=5,
        created_at="2024-01-01T00:00:00Z",
        expires_at=None,
        pinned=False,
    )
    manifest = Manifest(
        session_id=SessionId("sess_test"),
        created_at="2024-01-01T00:00:00Z",
        items=[item],
    )

    payload = manifest.to_dict()
    assert payload["session_id"] == "sess_test"
    assert payload["items"][0]["id"] == "tr_abc123"

    parsed = Manifest.from_dict(payload)
    assert parsed.session_id == SessionId("sess_test")
    assert parsed.items[0].id == ItemId("tr_abc123")
