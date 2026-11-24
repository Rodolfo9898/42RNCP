"""Reading the replies of OpenAI-compatible servers, tolerating the shapes that gateways produce."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from verdict.reviews.ai.contract import AIError, ModelUnavailable, clean


@dataclass
class Reply:
    status: int
    headers: httpx.Headers
    data: object  # parsed JSON body, or None when the body was not JSON


def json_or_none(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return None


def summarise_reply(data) -> str:
    """A short, safe description of a reply we could not read: its type, field names and any error text."""
    if not isinstance(data, dict):
        return f"a JSON {type(data).__name__}, not an object"
    parts = [f"fields: {', '.join(sorted(map(str, data))[:10]) or 'none'}"]
    for key in ("error", "detail", "message", "msg"):
        value = data.get(key)
        if isinstance(value, dict):
            value = value.get("message") or value.get("msg") or json.dumps(value)[:200]
        if value:
            parts.append(f"{key}: {clean(str(value), 200)}")
    return "; ".join(parts)


def _refuse_error_replies(data, redact: Callable[[str], str]) -> None:
    """A 200 that carries an error instead of an answer: the key is wrong (AIError) or the model is not serving (ModelUnavailable)."""
    if not isinstance(data, dict):
        return
    error = data.get("error") or data.get("detail")
    if error and not data.get("choices"):
        message = error.get("message") if isinstance(error, dict) else str(error)
        message = redact(clean(message or json.dumps(error), 200))
        if re.search(r"api key|unauthori[sz]ed|forbidden|invalid token|authenticat", message, re.I):
            raise AIError("The AI server rejected the API key (check LLM_API_KEY).")
        raise ModelUnavailable(f"The AI server answered 200 but reported an error: {message}")


def _choice(data) -> tuple[object, str | None]:
    """(text, finish reason) of the first choice, in any of the shapes the servers use."""
    choice = data["choices"][0]
    message = choice.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):  # content split into parts: [{"type": "text", "text": "..."}]
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    if not content and isinstance(message, dict):
        content = message.get("reasoning_content") or message.get("reasoning")  # reasoning models
    if not content:
        content = choice.get("text")  # old completion style
    return content, choice.get("finish_reason")


def reply_text(data, redact: Callable[[str], str] = lambda t: t) -> tuple[str, str | None]:
    """The model's text and finish reason from an OpenAI-style reply, tolerating the shapes gateways produce.

    Raises ModelUnavailable (so a fallback model can be tried) for replies that carry an error or no answer,
    and AIError when the server says the key is wrong.
    """
    _refuse_error_replies(data, redact)
    try:
        content, finish = _choice(data)
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ModelUnavailable(f"The AI server's answer had an unexpected shape ({redact(summarise_reply(data))}).") from None
    if not isinstance(content, str) or not content.strip():
        raise ModelUnavailable(f"The AI server's answer was empty ({redact(summarise_reply(data))}).")
    return content, finish
