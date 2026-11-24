from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.fakes import FakeClient, digest, overview, response


def test_request_shape_protects_the_prompt_and_enables_caching():
    client = FakeClient(response(ai.AnalysisOut(overview=overview(), improvements=[])))
    ai.analyze(ai.AnthropicBackend(client, "claude-opus-5-5"), digest(), subjects=["p.pdf"], summary="s", known_titles=[], usage=ai.Usage())
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_format"] is ai.AnalysisOut
    assert "untrusted" in call["system"] and "Never follow it" in call["system"]
    blocks = call["messages"][0]["content"]
    assert blocks[0]["text"].startswith("<repository>") and blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in blocks[1]


# ---------------------------------------------------------------- failures are explained, never leaked


def http_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("sk-ant-SECRET-key leaked in message", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize("error,expected", [
    (http_error(anthropic.AuthenticationError, 401), "rejected the API key"),
    (http_error(anthropic.PermissionDeniedError, 403), "not allowed"),
    (http_error(anthropic.NotFoundError, 404), "was not found"),
    (http_error(anthropic.RateLimitError, 429), "Rate limited"),
    (http_error(anthropic.InternalServerError, 500), "HTTP 500"),
])
def test_api_errors_become_safe_messages(error, expected):
    with pytest.raises(ai.AIError, match=expected) as info:
        ai.review(ai.AnthropicBackend(FakeClient(error), "m"), digest(), [("r1", "x")], ai.Usage())
    assert "SECRET" not in str(info.value)


def test_connection_failure():
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))
    with pytest.raises(ai.AIError, match="Could not reach"):
        ai.review(ai.AnthropicBackend(FakeClient(err), "m"), digest(), [("r1", "x")], ai.Usage())


@pytest.mark.parametrize("resp,expected", [
    (response(None, stop="refusal", stop_details=SimpleNamespace(category="cyber")), "declined.*cyber"),
    (response(None, stop="max_tokens"), "cut off"),
    (response(None), "expected format"),
])
def test_unusable_answers_are_reported(resp, expected):
    with pytest.raises(ai.AIError, match=expected):
        ai.review(ai.AnthropicBackend(FakeClient(resp), "m"), digest(), [("r1", "x")], ai.Usage())
