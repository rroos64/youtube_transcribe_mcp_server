from __future__ import annotations

import urllib.parse
from typing import Any

from .app import mcp
from .error_handling import handle_mcp_errors
from .payloads import build_prompt_payload
from .session import extract_session_id


@handle_mcp_errors
def template_reflow(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Reformat the transcript into well-structured paragraphs. Preserve speaker turns if present, "
        "remove stutters/obvious filler where it improves readability, and keep the original meaning."
    )
    return build_prompt_payload(
        name="paragraphs",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
    )


@handle_mcp_errors
def template_summary(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Summarize the transcript with:\n"
        "1) A one-paragraph executive summary.\n"
        "2) 5-8 bullet key points.\n"
        "Keep it concise and faithful to the source."
    )
    return build_prompt_payload(
        name="summary",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
    )


@handle_mcp_errors
def template_translate(item_id: str, target_lang: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    target_lang = urllib.parse.unquote(target_lang)
    prompt = (
        f"Translate the transcript to {target_lang}. Preserve proper nouns and technical terms. "
        "Keep formatting clean and readable."
    )
    return build_prompt_payload(
        name="translate",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
        extra_inputs={"target_lang": target_lang},
    )


@handle_mcp_errors
def template_outline(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Create a structured outline or table of contents for the transcript. "
        "Use short section headings and group related content."
    )
    return build_prompt_payload(
        name="outline",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
    )


@handle_mcp_errors
def template_quotes(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = (
        "Extract 5-10 quotable lines from the transcript. "
        "Each quote should be meaningful and stand alone."
    )
    return build_prompt_payload(
        name="quotes",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
    )


@handle_mcp_errors
def template_faq(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "Create a concise FAQ based on the transcript content. Provide short Q/A pairs."
    return build_prompt_payload(
        name="faq",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
    )


@handle_mcp_errors
def template_glossary(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "Extract key terms and provide a short glossary (term + 1-2 sentence definition)."
    return build_prompt_payload(
        name="glossary",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
    )


@handle_mcp_errors
def template_action_items(item_id: str, ctx: Any | None = None) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    prompt = "List action items or next steps implied by the transcript. Use clear, actionable phrasing."
    return build_prompt_payload(
        name="action_items",
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
    )


mcp.resource("template://transcript/paragraphs/{item_id}")(template_reflow)
mcp.resource("template://transcript/summary/{item_id}")(template_summary)
mcp.resource("template://transcript/translate/{item_id}/{target_lang}")(template_translate)
mcp.resource("template://transcript/outline/{item_id}")(template_outline)
mcp.resource("template://transcript/quotes/{item_id}")(template_quotes)
mcp.resource("template://transcript/faq/{item_id}")(template_faq)
mcp.resource("template://transcript/glossary/{item_id}")(template_glossary)
mcp.resource("template://transcript/action-items/{item_id}")(template_action_items)
