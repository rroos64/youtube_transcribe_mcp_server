import pytest

from yt_dlp_transcriber.domain.errors import (
    ExternalCommandError,
    ExpiredItemError,
    InvalidItemId,
    InvalidSessionId,
    NotFoundError,
)
from yt_dlp_transcriber.mcp.error_handling import handle_mcp_errors


@handle_mcp_errors
def _raise_invalid_session():
    raise InvalidSessionId("session_id must be 1-64 chars of letters, numbers, '-' or '_'")


@handle_mcp_errors
def _raise_invalid_item():
    raise InvalidItemId("item_id must be 1-64 chars of letters, numbers, '-' or '_'")


@handle_mcp_errors
def _raise_not_found():
    raise NotFoundError("Item not found")


@handle_mcp_errors
def _raise_external():
    raise ExternalCommandError("yt-dlp failed")


@handle_mcp_errors
def _raise_expired():
    raise ExpiredItemError("expired")


def test_invalid_session_maps_to_value_error():
    with pytest.raises(ValueError) as exc:
        _raise_invalid_session()
    assert "ERR_INVALID_SESSION" in str(exc.value)


def test_invalid_item_maps_to_value_error():
    with pytest.raises(ValueError) as exc:
        _raise_invalid_item()
    assert "ERR_INVALID_ITEM" in str(exc.value)


def test_not_found_maps_to_value_error():
    with pytest.raises(ValueError) as exc:
        _raise_not_found()
    assert "ERR_NOT_FOUND" in str(exc.value)


def test_external_command_maps_to_runtime_error():
    with pytest.raises(RuntimeError) as exc:
        _raise_external()
    assert "ERR_EXTERNAL_COMMAND" in str(exc.value)


def test_expired_item_maps_to_value_error():
    with pytest.raises(ValueError) as exc:
        _raise_expired()
    assert "ERR_EXPIRED_ITEM" in str(exc.value)
