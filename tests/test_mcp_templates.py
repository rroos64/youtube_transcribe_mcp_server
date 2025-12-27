import json

from yt_dlp_transcriber.mcp.templates import (
    template_action_items,
    template_faq,
    template_glossary,
    template_outline,
    template_quotes,
    template_reflow,
    template_translate,
)


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


def test_template_reflow_includes_session():
    ctx = {"mcp-session-id": "sess_reflow"}
    payload = template_reflow("tr_abc123", ctx=ctx)
    data = json.loads(payload)
    assert data["name"] == "paragraphs"
    assert data["inputs"]["session_id"] == "sess_reflow"


def test_template_quotes_uses_placeholder_session():
    payload = template_quotes("tr_abc123")
    data = json.loads(payload)
    assert data["name"] == "quotes"
    assert data["inputs"]["item_id"] == "tr_abc123"
    assert "YOUR_SESSION_ID" in data["recommended_steps"][0]


def test_template_faq_includes_inputs():
    ctx = {"mcp-session-id": "sess_faq"}
    payload = template_faq("tr_abc123", ctx=ctx)
    data = json.loads(payload)
    assert data["name"] == "faq"
    assert data["inputs"]["item_id"] == "tr_abc123"
    assert data["inputs"]["session_id"] == "sess_faq"


def test_template_glossary_includes_inputs():
    ctx = {"mcp-session-id": "sess_glossary"}
    payload = template_glossary("tr_abc123", ctx=ctx)
    data = json.loads(payload)
    assert data["name"] == "glossary"
    assert data["inputs"]["session_id"] == "sess_glossary"


def test_template_action_items_includes_inputs():
    ctx = {"mcp-session-id": "sess_actions"}
    payload = template_action_items("tr_abc123", ctx=ctx)
    data = json.loads(payload)
    assert data["name"] == "action_items"
    assert data["inputs"]["session_id"] == "sess_actions"
