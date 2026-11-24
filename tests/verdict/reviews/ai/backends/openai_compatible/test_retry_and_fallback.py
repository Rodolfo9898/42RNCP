import json

import httpx
import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.backends.openai_compatible.fakes import ANALYSIS, KEY, backend, completion, run_analysis


# ---------------------------------------------------------------- temporary failures: retry, then fall back


def test_temporary_503_is_retried_with_growing_pauses_then_succeeds():
    replies = [httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})] * 2 + [completion(json.dumps(ANALYSIS))]
    waits = []
    overview, _, _ = run_analysis(backend(lambda request: replies.pop(0), waits=waits))
    assert overview.purpose == "Prints ok." and waits == [2.0, 6.0]


def test_retry_after_is_honoured_but_capped():
    replies = [httpx.Response(429, headers={"retry-after": "10"}), httpx.Response(429, headers={"retry-after": "3600"}), completion(json.dumps(ANALYSIS))]
    waits = []
    run_analysis(backend(lambda request: replies.pop(0), waits=waits))
    assert waits == [15.0, 30.0]         # a rate limit waits at least 15s, never more than 30s


def test_persistent_503_without_fallback_reports_the_server_message():
    calls = []
    with pytest.raises(ai.ModelUnavailable, match="temporarily unavailable"):
        run_analysis(backend(lambda request: (calls.append(1), httpx.Response(503, json={"error": {"message": "The requested model is temporarily unavailable."}}))[1]))
    assert len(calls) == 3                                   # three attempts, then give up


def test_auth_and_client_errors_are_never_retried():
    for status in (400, 401, 403):
        calls = []
        with pytest.raises(ai.AIError):
            run_analysis(backend(lambda request, s=status: (calls.append(1), httpx.Response(s, text="no"))[1]))
        assert len(calls) <= 2                               # 400 may re-ask once without json mode; never 3


def test_falls_back_to_the_next_model_and_remembers_it():
    models = []

    def handler(request):
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "deepseek-v3":
            return httpx.Response(402, json={"error": {"message": "needs a balance"}})
        if model == "glm-4.7-flash":
            return httpx.Response(503, text="down")
        return completion(json.dumps(ANALYSIS))

    b = backend(handler, fallbacks=["glm-4.7-flash", "gpt-oss-20b"])
    run_analysis(b)
    assert b.model == "gpt-oss-20b"
    assert models[0] == "deepseek-v3" and models[-1] == "gpt-oss-20b" and models.count("glm-4.7-flash") == 3
    # the next request goes straight to the model that worked
    models.clear()
    run_analysis(b)
    assert models == ["gpt-oss-20b"]


def test_all_models_failing_lists_every_reason():
    b = backend(lambda request: httpx.Response(402, json={"error": {"message": "pay up"}}), fallbacks=["glm-4.7-flash"])
    with pytest.raises(ai.AIError, match="No configured model could answer") as info:
        run_analysis(b)
    text = str(info.value)
    assert "deepseek-v3" in text and "glm-4.7-flash" in text and "needs a paid balance" in text and KEY not in text


def test_a_rejected_key_does_not_trigger_the_fallback():
    models = []

    def handler(request):
        models.append(json.loads(request.content)["model"])
        return httpx.Response(401, text="bad key")

    with pytest.raises(ai.AIError, match="rejected the API key"):
        run_analysis(backend(handler, fallbacks=["glm-4.7-flash"]))
    assert models == ["deepseek-v3"]
