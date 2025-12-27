from __future__ import annotations

import urllib.parse

from .app import Context, mcp
from .error_handling import handle_mcp_errors
from .payloads import build_prompt_payload, build_prompt_text
from .session import extract_session_id


_READ_ONLY_HINTS = {"readOnlyHint": True, "idempotentHint": True}
_PARAGRAPHS_PROMPT = (
    "Reformat the transcript into well-structured paragraphs. Preserve speaker turns if present, "
    "remove stutters/obvious filler where it improves readability, and keep the original meaning."
)
_SUMMARY_PROMPT = (
    "Summarize the transcript with:\n"
    "1) A one-paragraph executive summary.\n"
    "2) 5-8 bullet key points.\n"
    "Keep it concise and faithful to the source."
)
_OUTLINE_PROMPT = (
    "Create a structured outline or table of contents for the transcript. "
    "Use short section headings and group related content."
)
_QUOTES_PROMPT = (
    "Extract 5-10 quotable lines from the transcript. "
    "Each quote should be meaningful and stand alone."
)
_FAQ_PROMPT = "Create a concise FAQ based on the transcript content. Provide short Q/A pairs."
_GLOSSARY_PROMPT = "Extract key terms and provide a short glossary (term + 1-2 sentence definition)."
_ACTION_ITEMS_PROMPT = (
    "List action items or next steps implied by the transcript. Use clear, actionable phrasing."
)


def _translate_prompt(target_lang: str) -> str:
    return (
        f"Translate the transcript to {target_lang}. Preserve proper nouns and technical terms. "
        "Keep formatting clean and readable."
    )


def _render_template(
    *,
    name: str,
    item_id: str,
    ctx: Context = None,
    prompt: str,
    extra_inputs: dict | None = None,
) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    return build_prompt_payload(
        name=name,
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
        extra_inputs=extra_inputs,
    )


def _render_prompt(
    *,
    name: str,
    item_id: str,
    ctx: Context = None,
    prompt: str,
    extra_inputs: dict | None = None,
) -> str:
    session_id = extract_session_id(ctx)
    item_id = urllib.parse.unquote(item_id)
    return build_prompt_text(
        name=name,
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
        extra_inputs=extra_inputs,
    )


@handle_mcp_errors
def template_reflow(item_id: str, ctx: Context = None) -> str:
    return _render_template(name="paragraphs", item_id=item_id, ctx=ctx, prompt=_PARAGRAPHS_PROMPT)


@handle_mcp_errors
def template_summary(item_id: str, ctx: Context = None) -> str:
    return _render_template(name="summary", item_id=item_id, ctx=ctx, prompt=_SUMMARY_PROMPT)


@handle_mcp_errors
def template_translate(item_id: str, target_lang: str, ctx: Context = None) -> str:
    target_lang = urllib.parse.unquote(target_lang)
    prompt = _translate_prompt(target_lang)
    return _render_template(
        name="translate",
        item_id=item_id,
        ctx=ctx,
        prompt=prompt,
        extra_inputs={"target_lang": target_lang},
    )


@handle_mcp_errors
def template_outline(item_id: str, ctx: Context = None) -> str:
    return _render_template(name="outline", item_id=item_id, ctx=ctx, prompt=_OUTLINE_PROMPT)


@handle_mcp_errors
def template_quotes(item_id: str, ctx: Context = None) -> str:
    return _render_template(name="quotes", item_id=item_id, ctx=ctx, prompt=_QUOTES_PROMPT)


@handle_mcp_errors
def template_faq(item_id: str, ctx: Context = None) -> str:
    return _render_template(name="faq", item_id=item_id, ctx=ctx, prompt=_FAQ_PROMPT)


@handle_mcp_errors
def template_glossary(item_id: str, ctx: Context = None) -> str:
    return _render_template(name="glossary", item_id=item_id, ctx=ctx, prompt=_GLOSSARY_PROMPT)


@handle_mcp_errors
def template_action_items(item_id: str, ctx: Context = None) -> str:
    return _render_template(
        name="action_items",
        item_id=item_id,
        ctx=ctx,
        prompt=_ACTION_ITEMS_PROMPT,
    )


@handle_mcp_errors
def prompt_paragraphs(item_id: str, ctx: Context = None) -> str:
    return _render_prompt(name="paragraphs", item_id=item_id, ctx=ctx, prompt=_PARAGRAPHS_PROMPT)


@handle_mcp_errors
def prompt_summary(item_id: str, ctx: Context = None) -> str:
    return _render_prompt(name="summary", item_id=item_id, ctx=ctx, prompt=_SUMMARY_PROMPT)


@handle_mcp_errors
def prompt_translate(item_id: str, target_lang: str, ctx: Context = None) -> str:
    target_lang = urllib.parse.unquote(target_lang)
    prompt = _translate_prompt(target_lang)
    return _render_prompt(
        name="translate",
        item_id=item_id,
        ctx=ctx,
        prompt=prompt,
        extra_inputs={"target_lang": target_lang},
    )


@handle_mcp_errors
def prompt_outline(item_id: str, ctx: Context = None) -> str:
    return _render_prompt(name="outline", item_id=item_id, ctx=ctx, prompt=_OUTLINE_PROMPT)


@handle_mcp_errors
def prompt_quotes(item_id: str, ctx: Context = None) -> str:
    return _render_prompt(name="quotes", item_id=item_id, ctx=ctx, prompt=_QUOTES_PROMPT)


@handle_mcp_errors
def prompt_faq(item_id: str, ctx: Context = None) -> str:
    return _render_prompt(name="faq", item_id=item_id, ctx=ctx, prompt=_FAQ_PROMPT)


@handle_mcp_errors
def prompt_glossary(item_id: str, ctx: Context = None) -> str:
    return _render_prompt(name="glossary", item_id=item_id, ctx=ctx, prompt=_GLOSSARY_PROMPT)


@handle_mcp_errors
def prompt_action_items(item_id: str, ctx: Context = None) -> str:
    return _render_prompt(
        name="action_items",
        item_id=item_id,
        ctx=ctx,
        prompt=_ACTION_ITEMS_PROMPT,
    )


mcp.resource(
    "template://transcript/paragraphs/{item_id}",
    annotations=_READ_ONLY_HINTS,
)(template_reflow)
mcp.resource(
    "template://transcript/summary/{item_id}",
    annotations=_READ_ONLY_HINTS,
)(template_summary)
mcp.resource(
    "template://transcript/translate/{item_id}/{target_lang}",
    annotations=_READ_ONLY_HINTS,
)(template_translate)
mcp.resource(
    "template://transcript/outline/{item_id}",
    annotations=_READ_ONLY_HINTS,
)(template_outline)
mcp.resource(
    "template://transcript/quotes/{item_id}",
    annotations=_READ_ONLY_HINTS,
)(template_quotes)
mcp.resource(
    "template://transcript/faq/{item_id}",
    annotations=_READ_ONLY_HINTS,
)(template_faq)
mcp.resource(
    "template://transcript/glossary/{item_id}",
    annotations=_READ_ONLY_HINTS,
)(template_glossary)
mcp.resource(
    "template://transcript/action-items/{item_id}",
    annotations=_READ_ONLY_HINTS,
)(template_action_items)

mcp.prompt("paragraphs")(prompt_paragraphs)
mcp.prompt("summary")(prompt_summary)
mcp.prompt("translate")(prompt_translate)
mcp.prompt("outline")(prompt_outline)
mcp.prompt("quotes")(prompt_quotes)
mcp.prompt("faq")(prompt_faq)
mcp.prompt("glossary")(prompt_glossary)
mcp.prompt("action_items")(prompt_action_items)
