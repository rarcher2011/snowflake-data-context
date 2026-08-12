"""Utilities for reading text from OpenAI response objects."""

from __future__ import annotations

from typing import Sequence


def extract_response_text(response: object) -> str:
    """Return the best available text from an OpenAI Responses API result."""

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = getattr(response, "output", None)
    if isinstance(output, list):
        text_parts = _extract_output_text_parts(output)
        if text_parts:
            return "\n".join(text_parts).strip()

    return str(response).strip()


def _extract_output_text_parts(output: Sequence[object]) -> list[str]:
    text_parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for content_item in content:
            text = getattr(content_item, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
    return text_parts
