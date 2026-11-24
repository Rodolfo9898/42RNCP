"""Plain text helpers for what comes back from a model."""

from __future__ import annotations

import re


def clean(text: str, limit: int) -> str:
    """Control characters removed, cut to `limit` characters."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def extract_json(text: str) -> str:
    """The JSON object in a model reply that may carry code fences, <think> blocks or chatter."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text
