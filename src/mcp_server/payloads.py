from __future__ import annotations

import json


def json_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _build_prompt_data(
    *,
    name: str,
    item_id: str,
    session_id: str | None,
    prompt: str,
    extra_inputs: dict | None = None,
) -> dict:
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
    return payload


def build_prompt_payload(
    *,
    name: str,
    item_id: str,
    session_id: str | None,
    prompt: str,
    extra_inputs: dict | None = None,
) -> str:
    return json_payload(
        _build_prompt_data(
            name=name,
            item_id=item_id,
            session_id=session_id,
            prompt=prompt,
            extra_inputs=extra_inputs,
        )
    )


def build_prompt_text(
    *,
    name: str,
    item_id: str,
    session_id: str | None,
    prompt: str,
    extra_inputs: dict | None = None,
) -> str:
    data = _build_prompt_data(
        name=name,
        item_id=item_id,
        session_id=session_id,
        prompt=prompt,
        extra_inputs=extra_inputs,
    )
    inputs = data["inputs"]
    input_str = ", ".join(f"{key}={value}" for key, value in inputs.items())
    steps = "\n".join(f"- {step}" for step in data["recommended_steps"])
    sections = [data["prompt"]]
    if input_str:
        sections.append(f"\nInputs: {input_str}")
    sections.append(f"\nSteps:\n{steps}")
    return "\n".join(sections)
