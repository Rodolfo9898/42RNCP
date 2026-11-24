import json

import httpx
import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.backends.openai_compatible.fakes import ANALYSIS, KEY, backend, completion, digest, run_analysis


# ---------------------------------------------------------------- the request


def test_request_goes_to_chat_completions_with_the_key_and_the_schema():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        return completion(json.dumps(ANALYSIS))

    overview, improvements, usage = run_analysis(backend(handler))
    assert seen["url"] == "https://api.airforce/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    body = seen["body"]
    assert body["model"] == "deepseek-v3" and body["stream"] is False and body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system" and "untrusted" in body["messages"][0]["content"]
    assert "<repository>" in body["messages"][1]["content"] and "JSON Schema" in body["messages"][1]["content"]
    assert KEY not in json.dumps(body)                       # the key travels in the header only
    assert (usage.input_tokens, usage.output_tokens) == (1200, 300)
    assert overview.purpose == "Prints ok."
    assert [(e.file, e.line) for e in improvements[0].evidence] == [("main.c", 1)]   # invented.c was dropped


@pytest.mark.parametrize("reply", [
    "```json\n{PAYLOAD}\n```",
    "Sure! Here is the analysis:\n{PAYLOAD}\nHope this helps.",
    "<think>let me think about the repository...</think>{PAYLOAD}",
])
def test_models_that_wrap_their_json_are_tolerated(reply):
    text = reply.replace("{PAYLOAD}", json.dumps(ANALYSIS))
    overview, _, _ = run_analysis(backend(lambda request: completion(text)))
    assert overview.languages == ["C"]


def test_one_corrective_retry_for_invalid_output():
    replies = [completion("this is not json"), completion(json.dumps(ANALYSIS))]
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return replies.pop(0)

    overview, _, usage = run_analysis(backend(handler))
    assert overview.purpose == "Prints ok." and len(bodies) == 2
    assert bodies[1]["messages"][-1]["role"] == "user" and "not valid" in bodies[1]["messages"][-1]["content"]
    assert usage.input_tokens == 2400                         # both attempts are counted


def test_gives_up_after_the_retry():
    with pytest.raises(ai.AIError, match="did not return valid JSON"):
        run_analysis(backend(lambda request: completion('{"overview": 1}')))


def test_servers_without_json_mode_are_retried_without_it():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append("response_format" in body)
        return httpx.Response(400, json={"error": {"message": "unsupported"}}) if "response_format" in body else completion(json.dumps(ANALYSIS))

    run_analysis(backend(handler))
    assert calls == [True, False]


def test_truncated_answers_are_reported():
    with pytest.raises(ai.AIError, match="cut off"):
        run_analysis(backend(lambda request: completion('{"overview": {"purpose": "x', finish="length")))


def test_review_batches_are_smaller_for_these_models():
    assert ai.OpenAIBackend.batch == 10 < ai.AnthropicBackend.batch
    seen = []

    def handler(request):
        text = json.loads(request.content)["messages"][1]["content"]
        ids = [i for i in (f"r{n}" for n in range(25)) if f'<subject_item id="{i}">' in text]
        seen.append(len(ids))
        return completion(json.dumps({"items": [{"rule_id": i, "assessment": "likely_ok", "why_manual": "w", "finding": "f", "evidence": []} for i in ids]}))

    reviews = ai.review(backend(handler), digest(), [(f"r{n}", f"Requirement {n}.") for n in range(25)], ai.Usage())
    assert seen == [10, 10, 5] and len(reviews) == 25


# ---------------------------------------------------------------- failures are explained, never leak the key


@pytest.mark.parametrize("response,expected", [
    (httpx.Response(401, json={"error": {"message": f"bad key {KEY}"}}), "rejected the API key"),
    (httpx.Response(403, text="forbidden"), "rejected the API key"),
    (httpx.Response(404, json={"error": {"message": "no such model"}}), "does not know"),
    (httpx.Response(429, text="slow down"), "Rate limited"),
    (httpx.Response(500, json={"error": {"message": f"upstream exploded for {KEY}"}}), "HTTP 500\\): upstream exploded for \\*\\*\\*"),
    (httpx.Response(200, text="<html>Welcome to my proxy</html>"), "not JSON"),
    (httpx.Response(200, json={"unexpected": True}), "unexpected shape"),
])
def test_http_failures(response, expected):
    with pytest.raises(ai.AIError, match=expected) as info:
        run_analysis(backend(lambda request: response))
    assert KEY not in str(info.value)


def test_network_failures():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ai.AIError, match="did not answer in time"):
        run_analysis(backend(timeout))
    with pytest.raises(ai.AIError, match="Could not reach the AI server"):
        run_analysis(backend(refused))
