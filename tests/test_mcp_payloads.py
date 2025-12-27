import json

from mcp_server.payloads import build_prompt_payload, json_payload


def test_json_payload_round_trip():
    payload = {"name": "test", "value": 123}
    rendered = json_payload(payload)
    assert json.loads(rendered) == payload


def test_build_prompt_payload_includes_inputs_and_steps():
    rendered = build_prompt_payload(
        name="summary",
        item_id="tr_123",
        session_id="sess_abc",
        prompt="Prompt text",
        extra_inputs={"target_lang": "en"},
    )
    data = json.loads(rendered)

    assert data["name"] == "summary"
    assert data["prompt"] == "Prompt text"
    assert data["inputs"]["item_id"] == "tr_123"
    assert data["inputs"]["session_id"] == "sess_abc"
    assert data["inputs"]["target_lang"] == "en"
    assert "transcripts://session/sess_abc/item/tr_123" in data["recommended_steps"][0]
    assert "read_file_chunk" in data["recommended_steps"][1]


def test_build_prompt_payload_uses_placeholder_session():
    rendered = build_prompt_payload(
        name="summary",
        item_id="tr_123",
        session_id=None,
        prompt="Prompt text",
    )
    data = json.loads(rendered)

    assert data["inputs"] == {"item_id": "tr_123"}
    assert "YOUR_SESSION_ID" in data["recommended_steps"][0]
