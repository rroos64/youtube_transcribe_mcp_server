import json

from yt_dlp_transcriber.mcp.templates import template_outline, template_translate


def test_template_translate_includes_target_lang_and_session():
    ctx = {"mcp-session-id": "sess_translate"}
    payload = template_translate("tr_abc123", "French%20CA", ctx=ctx)
    data = json.loads(payload)

    assert data["name"] == "translate"
    assert data["inputs"]["item_id"] == "tr_abc123"
    assert data["inputs"]["session_id"] == "sess_translate"
    assert data["inputs"]["target_lang"] == "French CA"
    assert "transcripts://session/sess_translate/item/tr_abc123" in data["recommended_steps"][0]


def test_template_outline_uses_placeholder_session():
    payload = template_outline("tr_abc123")
    data = json.loads(payload)
    assert data["inputs"]["item_id"] == "tr_abc123"
    assert "YOUR_SESSION_ID" in data["recommended_steps"][0]
