import pytest

from mcp_server.session import extract_session_id, get_session_id


class DummyHeaders:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class DummyRequest:
    def __init__(self, headers):
        self.headers = headers


class DummyCtx:
    def __init__(self, session_id=None, headers=None, request=None):
        self.session_id = session_id
        self.headers = headers
        self.request = request


def test_extract_session_id_prefers_dict_keys():
    ctx = {"mcp_session_id": "sess_dict"}
    assert extract_session_id(ctx) == "sess_dict"


def test_extract_session_id_from_attributes_and_headers():
    ctx = DummyCtx(session_id="sess_attr")
    assert extract_session_id(ctx) == "sess_attr"

    headers_ctx = DummyCtx(headers=DummyHeaders({"x-mcp-session-id": "sess_hdr"}))
    assert extract_session_id(headers_ctx) == "sess_hdr"

    class RequestOnlyCtx:
        def __init__(self, request):
            self.request = request

    request_ctx = RequestOnlyCtx(DummyRequest(DummyHeaders({"MCP-Session-Id": "sess_req"})))
    assert extract_session_id(request_ctx) == "sess_req"


def test_get_session_id_mismatch_raises():
    ctx = {"mcp-session-id": "sess_ctx"}
    with pytest.raises(ValueError):
        get_session_id(session_id="sess_other", ctx=ctx, default_session_id="")


def test_get_session_id_default_and_optional():
    assert str(get_session_id(default_session_id="sess_default")) == "sess_default"
    assert get_session_id(required=False) is None
