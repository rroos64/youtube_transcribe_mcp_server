import pytest

from adapters.filesystem_store import SessionStore
from adapters.manifest_json_repo import ManifestRepository
from domain.errors import (
    ExternalCommandError,
    InvalidItemId,
    InvalidSessionId,
    NotFoundError,
)
from domain.types import ItemId, SessionId
from services.session_service import SessionService


def test_error_hierarchy():
    assert issubclass(InvalidSessionId, ValueError)
    assert issubclass(InvalidItemId, ValueError)
    assert issubclass(NotFoundError, ValueError)
    assert issubclass(ExternalCommandError, RuntimeError)


def test_invalid_ids_raise_typed_errors():
    with pytest.raises(InvalidSessionId):
        SessionId("bad id")

    with pytest.raises(InvalidItemId):
        ItemId("")


def test_missing_item_raises_not_found(tmp_path):
    store = SessionStore(tmp_path)
    repo = ManifestRepository(store, default_ttl_sec=3600)
    service = SessionService(store, repo)

    with pytest.raises(NotFoundError):
        service.delete_item("missing", session_id="sess_missing")
