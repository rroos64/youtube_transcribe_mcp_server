from __future__ import annotations

import json


def json_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def build_prompt_payload(
    *,
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
    return json_payload(payload)
