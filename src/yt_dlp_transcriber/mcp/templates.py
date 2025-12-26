from __future__ import annotations

import json
import urllib.parse
from typing import Any

from .app import mcp
from .session import extract_session_id


def _encode_prompt_payload(
    name: str,
    item_id: str,
    session_id: str | None,
    prompt: str,
    extra_inputs: dict | None = None,
) -> str:
    inputs: dict = {"item_id": item_id}
    if session_id:
        inputs["session_id"] = session_id
    if extra_inputs:
        inputs.update(extra_inputs)

    sid_value = session_id or "YOUR_SESSION_ID"
    steps = [
        f"Call transcripts://session/{sid_value}/item/{item_id} to get metadata and inline content.",
        (
            "If content is missing or truncated, call "
            f"read_file_chunk(item_id=\"{item_id}\", session_id=\"{sid_value}\", "
            "offset=0, max_bytes=200000) until eof."
        ),
        "Complete the task and output only the result.",
        f"If you need this transcript later, call pin_item(item_id=\"{item_id}\").",
    ]

    payload = {
        "name": name,
        "inputs": inputs,
        "prompt": prompt,
        "recommended_steps": steps,
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.resource("template://transcript/paragraphs/{item_id}")
def template_reflow(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Reformat the transcript into well-structured paragraphs. Preserve speaker turns if present, "
        "remove stutters/obvious filler where it improves readability, and keep the original meaning."
    )
    return _encode_prompt_payload("paragraphs", item_id, session_id, prompt)


@mcp.resource("template://transcript/summary/{item_id}")
def template_summary(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Summarize the transcript with:\n"
        "1) A one-paragraph executive summary.\n"
        "2) 5-8 bullet key points.\n"
        "Keep it concise and faithful to the source."
    )
    return _encode_prompt_payload("summary", item_id, session_id, prompt)


@mcp.resource("template://transcript/translate/{item_id}/{target_lang}")
def template_translate(item_id: str, target_lang: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    target_lang = urllib.parse.unquote(target_lang)
    prompt = (
        f"Translate the transcript to {target_lang}. Preserve proper nouns and technical terms. "
        "Keep formatting clean and readable."
    )
    return _encode_prompt_payload("translate", item_id, session_id, prompt, {"target_lang": target_lang})


@mcp.resource("template://transcript/outline/{item_id}")
def template_outline(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Create a structured outline or table of contents for the transcript. "
        "Use short section headings and group related content."
    )
    return _encode_prompt_payload("outline", item_id, session_id, prompt)


@mcp.resource("template://transcript/quotes/{item_id}")
def template_quotes(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Extract 5-10 quotable lines from the transcript. "
        "Each quote should be meaningful and stand alone."
    )
    return _encode_prompt_payload("quotes", item_id, session_id, prompt)


@mcp.resource("template://transcript/faq/{item_id}")
def template_faq(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "Create a concise FAQ based on the transcript content. Provide short Q/A pairs."
    return _encode_prompt_payload("faq", item_id, session_id, prompt)


@mcp.resource("template://transcript/glossary/{item_id}")
def template_glossary(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "Extract key terms and provide a short glossary (term + 1-2 sentence definition)."
    return _encode_prompt_payload("glossary", item_id, session_id, prompt)


@mcp.resource("template://transcript/action-items/{item_id}")
def template_action_items(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "List action items or next steps implied by the transcript. Use clear, actionable phrasing."
    return _encode_prompt_payload("action_items", item_id, session_id, prompt)
