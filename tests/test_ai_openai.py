import json

import httpx
import pytest

from verdict import ai
from verdict.digest import Digest

KEY = "sk-air-SECRET-1234567890"


def digest():
    return Digest(text="<repository>\n<file path=\"main.c\" lines=\"5\">\n    1| int main(void)\n</file>\n</repository>",
                  lines={"main.c": 5, "Makefile": 3}, included=["main.c"])


def backend(handler, base="https://api.airforce/v1", key=KEY, fallbacks=None, waits=None):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    record = waits if waits is not None else []
    return ai.OpenAIBackend(base, key, "deepseek-v3", http=http, fallbacks=fallbacks, sleep=record.append)


def completion(content, finish="stop", prompt=1200, out=300):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
                                     "usage": {"prompt_tokens": prompt, "completion_tokens": out}})


ANALYSIS = {
    "overview": {"purpose": "Prints ok.", "languages": ["C"], "build_and_run": "make", "components": [{"path": "main.c", "role": "entry"}],
                 "notable": [], "not_found": ["README.md"]},
    "improvements": [{"category": "logic", "priority": "high", "title": "Unchecked write", "detail": "d",
                      "evidence": [{"file": "main.c", "line": 1}, {"file": "invented.c", "line": 4}]}],
}


def run_analysis(b):
    usage = ai.Usage()
    overview, improvements = ai.analyze(b, digest(), subjects=["p.pdf"], summary="s", known_titles=[], usage=usage)
    return overview, improvements, usage


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


# ---------------------------------------------------------------- configuration


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_base_url_selects_the_openai_compatible_provider(clean_env):
    assert ai.provider() == "anthropic" and not ai.configured()
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    assert ai.provider() == "openai"
    assert not ai.configured()                                 # still needs a key and a model
    clean_env.setenv("LLM_API_KEY", KEY)
    assert not ai.configured()
    clean_env.setenv("LLM_MODEL", "deepseek-v3")
    assert ai.configured() and ai.model_name() == "deepseek-v3" and ai.endpoint_host() == "api.airforce"


def test_a_local_server_needs_no_key(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1")
    clean_env.setenv("LLM_MODEL", "llama3.1")
    assert ai.configured()


def test_an_anthropic_key_alone_keeps_the_default_provider(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "k")
    assert ai.provider() == "anthropic" and ai.configured() and ai.endpoint_host() == "api.anthropic.com"
    clean_env.setenv("LLM_PROVIDER", "openai")
    assert not ai.configured()                                 # explicitly asked for the other provider, which is not set up


@pytest.mark.parametrize("url", ["http://api.airforce/v1", "ftp://x/v1", "api.airforce/v1", "https://", ""])
def test_unsafe_or_malformed_base_urls_are_refused(url):
    with pytest.raises(ai.AIError):
        ai.OpenAIBackend(url, KEY, "m")


def test_make_client_builds_the_selected_backend(clean_env):
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    clean_env.setenv("LLM_API_KEY", KEY)
    clean_env.setenv("LLM_MODEL", "deepseek-v3")
    backend_ = ai.make_client()
    assert isinstance(backend_, ai.OpenAIBackend) and backend_.url == "https://api.airforce/v1/chat/completions"
    clean_env.delenv("LLM_BASE_URL")
    clean_env.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(ai.make_client(), ai.AnthropicBackend)


def test_api_health_reports_the_provider(clean_env, tmp_path):
    from fastapi.testclient import TestClient
    clean_env.setenv("WORKSPACE", str(tmp_path / "ws"))
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    clean_env.setenv("LLM_API_KEY", KEY)
    clean_env.setenv("LLM_MODEL", "deepseek-v3")
    import importlib

    import verdict.main as main
    importlib.reload(main)
    health = TestClient(main.app).get("/api/health").json()["llm"]
    assert health == {"configured": True, "model": "deepseek-v3", "provider": "openai", "host": "api.airforce"}
    assert KEY not in json.dumps(health)


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


def test_fallback_models_come_from_the_environment(clean_env):
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    clean_env.setenv("LLM_API_KEY", KEY)
    clean_env.setenv("LLM_MODEL", "glm-4.7-flash")
    clean_env.setenv("LLM_FALLBACK_MODELS", " gpt-oss-20b, glm-4.7-flash ,mistral-large-latest,,")
    assert ai.fallback_models() == ["gpt-oss-20b", "mistral-large-latest"]     # the main model is not repeated
    made = ai.make_client()
    assert made.model == "glm-4.7-flash" and made.fallbacks == ["gpt-oss-20b", "mistral-large-latest"]


# ---------------------------------------------------------------- odd but real-world reply shapes


def reply(payload):
    return httpx.Response(200, json=payload)


def test_content_given_as_parts_is_joined():
    parts = [{"type": "text", "text": json.dumps(ANALYSIS)[:40]}, {"type": "text", "text": json.dumps(ANALYSIS)[40:]}]
    overview, _, _ = run_analysis(backend(lambda r: reply({"choices": [{"message": {"content": parts}, "finish_reason": "stop"}]})))
    assert overview.purpose == "Prints ok."


def test_reasoning_models_that_leave_content_empty():
    payload = {"choices": [{"message": {"content": None, "reasoning_content": "thinking... " + json.dumps(ANALYSIS)}, "finish_reason": "stop"}]}
    overview, _, _ = run_analysis(backend(lambda r: reply(payload)))
    assert overview.languages == ["C"]


def test_completion_style_text_field():
    overview, _, _ = run_analysis(backend(lambda r: reply({"choices": [{"text": json.dumps(ANALYSIS)}]})))
    assert overview.purpose == "Prints ok."


@pytest.mark.parametrize("payload,expected", [
    ({"error": {"message": "The model is overloaded, try later"}}, "reported an error: The model is overloaded"),
    ({"error": "quota exceeded"}, "reported an error: quota exceeded"),
    ({"detail": "Not found"}, "reported an error: Not found"),
    ({"choices": [], "id": "x", "object": "chat.completion"}, r"unexpected shape \(fields: choices, id, object\)"),
    ({"unexpected": True}, r"unexpected shape \(fields: unexpected\)"),
    ([1, 2, 3], r"unexpected shape \(a JSON list, not an object\)"),
    ({"choices": [{"message": {"content": "   "}, "finish_reason": "stop"}], "model": "m"}, r"answer was empty \(fields: choices, model\)"),
])
def test_unreadable_replies_say_what_arrived(payload, expected):
    with pytest.raises(ai.ModelUnavailable, match=expected):
        run_analysis(backend(lambda r: reply(payload)))


def test_a_200_that_means_bad_key_is_not_retried_or_fallen_back():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content)["model"])
        return reply({"error": {"message": "Invalid API key provided"}})

    with pytest.raises(ai.AIError, match="rejected the API key") as info:
        run_analysis(backend(handler, fallbacks=["glm-4.7-flash"]))
    assert not isinstance(info.value, ai.ModelUnavailable) and calls == ["deepseek-v3"]


def test_a_broken_reply_moves_on_to_the_fallback_model():
    def handler(request):
        if json.loads(request.content)["model"] == "deepseek-v3":
            return reply({"choices": []})
        return completion(json.dumps(ANALYSIS))

    b = backend(handler, fallbacks=["glm-4.7-flash"])
    run_analysis(b)
    assert b.model == "glm-4.7-flash"


def test_the_key_is_redacted_from_what_we_report():
    with pytest.raises(ai.ModelUnavailable) as info:
        run_analysis(backend(lambda r: reply({"error": {"message": f"token {KEY} is out of quota"}})))
    assert KEY not in str(info.value) and "***" in str(info.value)


# ---------------------------------------------------------------- notifications and cancellation


def test_every_step_of_a_retry_and_fallback_is_announced():
    messages = []
    replies = {"deepseek-v3": [httpx.Response(503, text="down")] * 3}

    def handler(request):
        model = json.loads(request.content)["model"]
        return replies[model].pop(0) if model in replies else completion(json.dumps(ANALYSIS))

    b = backend(handler, fallbacks=["glm-4.7-flash"])
    b.job = ai.Job(notify=messages.append)
    run_analysis(b)
    assert messages[0] == "Step 1: describing the repository and looking for improvements" or messages[0].startswith("Asking deepseek-v3")
    joined = "\n".join(messages)
    assert "Asking deepseek-v3 (try 1 of 3)" in joined and "answered HTTP 503" in joined
    assert "retrying in 2s" in joined and "retrying in 6s" in joined
    assert "deepseek-v3 is unavailable" in joined and "switching to glm-4.7-flash" in joined
    assert messages[-1].startswith("glm-4.7-flash answered HTTP 200")


def test_a_cancel_interrupts_a_request_that_never_returns():
    import threading
    import time
    release = threading.Event()

    def hang(request):
        release.wait(10)
        return completion(json.dumps(ANALYSIS))

    b = backend(hang)
    b.job = ai.Job()
    threading.Timer(0.3, b.job.cancel.set).start()
    start = time.monotonic()
    with pytest.raises(ai.Cancelled):
        run_analysis(b)
    assert time.monotonic() - start < 3
    release.set()


def test_a_cancel_during_the_pause_between_retries_wakes_up_at_once():
    import threading
    import time
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, headers={"retry-after": "30"}, text="busy")))
    b = ai.OpenAIBackend("https://api.airforce/v1", KEY, "m", http=http)        # real (interruptible) sleep
    b.job = ai.Job()
    threading.Timer(0.3, b.job.cancel.set).start()
    start = time.monotonic()
    with pytest.raises(ai.Cancelled):
        run_analysis(b)
    assert time.monotonic() - start < 3


# ---------------------------------------------------------------- streaming


def sse(*chunks, done=True):
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + (["data: [DONE]\n\n"] if done else [])
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="".join(lines).encode())


def delta(content=None, reasoning=None, finish=None):
    d = {k: v for k, v in (("content", content), ("reasoning_content", reasoning)) if v is not None}
    return {"choices": [{"delta": d, "finish_reason": finish}]}


def streaming_backend(handler, **kw):
    b = backend(handler, **kw)
    b.stream = True
    return b


def test_streamed_answer_is_assembled_and_the_request_asks_for_a_stream():
    text = json.dumps(ANALYSIS)
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return sse(delta(reasoning="hmm, "), delta(reasoning="let me think"), delta(content=text[:30]), delta(content=text[30:]),
                   delta(finish="stop"), {"choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 250}})

    messages = []
    b = streaming_backend(handler)
    b.job = ai.Job(notify=messages.append)
    overview, _, usage = run_analysis(b)
    assert seen["stream"] is True and overview.purpose == "Prints ok."
    assert (usage.input_tokens, usage.output_tokens) == (900, 250)
    assert any("(streaming)" in m for m in messages)


def test_streaming_reports_how_much_has_arrived(monkeypatch):
    clock = iter([0.0, 0.0, 1.0, 4.0, 4.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0])
    monkeypatch.setattr(ai.time, "monotonic", lambda: next(clock, 9.0))
    messages = []
    text = json.dumps(ANALYSIS)
    b = streaming_backend(lambda r: sse(delta(reasoning="x" * 50), delta(content=text[:20]), delta(content=text[20:]), delta(finish="stop")))
    b.job = ai.Job(notify=messages.append)
    run_analysis(b)
    receiving = [m for m in messages if m.startswith("Receiving the answer from deepseek-v3")]
    assert receiving and "characters written" in receiving[0] and "characters of reasoning" in receiving[0]


def test_a_server_that_ignores_stream_still_works():
    overview, _, _ = run_analysis(streaming_backend(lambda r: completion(json.dumps(ANALYSIS))))
    assert overview.purpose == "Prints ok."


def test_an_error_in_the_middle_of_a_stream_is_a_model_failure():
    with pytest.raises(ai.ModelUnavailable, match="reported an error: upstream died"):
        run_analysis(streaming_backend(lambda r: sse(delta(content='{"overview"'), {"error": {"message": "upstream died"}})))


def test_http_errors_are_handled_the_same_when_streaming():
    replies = [httpx.Response(503, text="down"), httpx.Response(503, text="down"), sse(delta(content=json.dumps(ANALYSIS)), delta(finish="stop"))]
    waits = []
    run_analysis(streaming_backend(lambda r: replies.pop(0), waits=waits))
    assert waits == [2.0, 6.0]
    with pytest.raises(ai.AIError, match="rejected the API key"):
        run_analysis(streaming_backend(lambda r: httpx.Response(401, text="no")))


def test_a_stream_that_is_cut_off_after_partial_output_is_reported_as_cut_off():
    with pytest.raises(ai.AIError, match="cut off"):
        run_analysis(streaming_backend(lambda r: sse(delta(content='{"overview": {"purpose": "x'), delta(finish="length"))))


def test_cancel_stops_reading_a_stream():
    b = streaming_backend(lambda r: sse(delta(content="{"), delta(content="}")))
    b.job = ai.Job()
    b.job.cancel.set()
    with pytest.raises(ai.Cancelled):
        run_analysis(b)


def test_streaming_is_switched_on_from_the_environment(clean_env):
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    clean_env.setenv("LLM_API_KEY", KEY)
    clean_env.setenv("LLM_MODEL", "m")
    assert ai.make_client().stream is False
    clean_env.setenv("LLM_STREAM", "true")
    assert ai.make_client().stream is True
