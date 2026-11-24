"""What the Anthropic client raises, and what its answers can be, in words that are safe to show."""

from __future__ import annotations

import anthropic

from verdict.reviews.ai.contract import AIError

API_ERRORS = (anthropic.APIConnectionError, anthropic.APIStatusError)


def explain(exc: Exception, model: str) -> AIError:
    """The AIError for a failed request (never the client's own message: it can carry the key)."""
    if isinstance(exc, anthropic.AuthenticationError):
        return AIError("Anthropic rejected the API key (check ANTHROPIC_API_KEY).")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return AIError("The API key is not allowed to use this model.")
    if isinstance(exc, anthropic.NotFoundError):
        return AIError(f"Model {model!r} was not found (check LLM_MODEL).")
    if isinstance(exc, anthropic.RateLimitError):
        return AIError("Rate limited by the API. Wait a minute and try again.")
    if isinstance(exc, anthropic.APIConnectionError):
        return AIError("Could not reach the Anthropic API from the container (network or timeout).")
    return AIError(f"The API returned an error (HTTP {exc.status_code}).")


def usable_answer(response):
    """The parsed answer, or an AIError saying why there is none."""
    if response.stop_reason == "refusal":
        category = getattr(getattr(response, "stop_details", None), "category", None)
        raise AIError("The model declined to analyse this repository" + (f" (category: {category})." if category else "."))
    if response.stop_reason == "max_tokens":
        raise AIError("The model's answer was cut off. Try again; if it persists the repository is too large.")
    if response.parsed_output is None:
        raise AIError("The model returned an answer that did not match the expected format.")
    return response.parsed_output
