import json
import threading
import time

import httpx
import pytest

from verdict import ai

ANALYSIS = {
    "overview": {"purpose": "Sorts stacks.", "languages": ["C"], "build_and_run": "make", "components": [{"path": "main.c", "role": "entry"}],
                 "notable": [], "not_found": []},
    "improvements": [{"category": "logic", "priority": "high", "title": "Unchecked malloc", "detail": "d",
                      "evidence": [{"file": "main.c", "line": 2}, {"file": "ghost.c", "line": 1}]}],
}


class Digest:
    text = ""
    lines = {"main.c": 10}


def service(handler):
    closed = []

    def new_client():                      # the backend makes (and closes) a fresh client for every request
        client = httpx.Client(transport=httpx.MockTransport(handler))
        original = client.close
        client.close = lambda: (closed.append(1), original())[1]
        return client

    backend = ai.ClaudeCliBackend("http://terminal:8002", "tok", "42/ps", "", http_factory=new_client)
    backend.closed = closed
    return backend


def reply(stdout, stderr="", returncode=0):
    return httpx.Response(200, json={"returncode": returncode, "stdout": stdout, "stderr": stderr})


def analyze(b):
    usage = ai.Usage()
    result = ai.analyze(b, Digest(), subjects=["p.pdf"], summary="s", known_titles=[], usage=usage)
    return result, usage


def test_request_carries_the_repo_prompt_schema_and_token():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), token=request.headers["x-terminal-token"], body=json.loads(request.content))
        return reply(json.dumps({"type": "result", "structured_output": ANALYSIS, "usage": {"input_tokens": 700, "output_tokens": 90}}))

    ((overview, improvements), usage) = analyze(service(handler))
    assert seen["url"] == "http://terminal:8002/review" and seen["token"] == "tok"
    body = seen["body"]
    assert body["repo"] == "42/ps" and body["model"] is None and "untrusted" in body["prompt"]
    assert "Read, Grep and Glob" in body["prompt"] and body["schema"]["type"] == "object"
    assert overview.purpose == "Sorts stacks." and (usage.input_tokens, usage.output_tokens) == (700, 90)
    assert [(e.file, e.line) for e in improvements[0].evidence] == [("main.c", 2)]       # ghost.c is dropped


@pytest.mark.parametrize("stdout", [
    json.dumps({"type": "result", "result": json.dumps(ANALYSIS)}),
    json.dumps({"result": "Here you go:\n```json\n" + json.dumps(ANALYSIS) + "\n```"}),
    json.dumps([{"type": "system"}, {"type": "assistant"}, {"type": "result", "subtype": "success", "result": json.dumps(ANALYSIS)}]),
    json.dumps(ANALYSIS),
    "Sure! " + json.dumps(ANALYSIS),
    json.dumps({"type": "result", "structured_output": json.dumps(ANALYSIS)}),
])
def test_every_plausible_output_shape_is_understood(stdout):
    ((overview, _), _) = analyze(service(lambda r: reply(stdout)))
    assert overview.languages == ["C"]


def test_unreadable_output_is_reported_not_guessed():
    with pytest.raises(ai.AIError, match="not in the expected JSON format"):
        analyze(service(lambda r: reply(json.dumps({"result": "I could not do that."}))))


def test_claude_errors_are_passed_on_briefly():
    with pytest.raises(ai.AIError, match="claude reported an error: Max turns"):
        analyze(service(lambda r: reply(json.dumps({"type": "result", "is_error": True, "result": "Max turns reached"}))))
    with pytest.raises(ai.AIError, match="exited with an error: boom"):
        analyze(service(lambda r: reply("", stderr="boom", returncode=2)))


@pytest.mark.parametrize("stdout,stderr", [
    ("", "Not logged in · Please run /login"),
    (json.dumps({"is_error": True, "result": "Invalid API key · Please run /login"}), ""),
])
def test_not_signed_in_tells_you_what_to_do(stdout, stderr):
    with pytest.raises(ai.AIError, match="not signed in.*Terminal tab.*/login"):
        analyze(service(lambda r: reply(stdout, stderr)))


@pytest.mark.parametrize("response,expected", [
    (httpx.Response(401, json={"detail": "bad token"}), "TERMINAL_TOKEN mismatch"),
    (httpx.Response(504, json={"detail": "slow"}), "did not finish in time"),
    (httpx.Response(400, json={"detail": "repository not found"}), "refused the review: repository not found"),
])
def test_service_errors(response, expected):
    with pytest.raises(ai.AIError, match=expected):
        analyze(service(lambda r: response))


def test_service_down():
    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ai.AIError, match="Could not reach the terminal service"):
        analyze(service(refused))


def test_cancel_drops_the_connection_so_the_service_stops_claude():
    release = threading.Event()

    def hang(request):
        release.wait(10)
        return reply(json.dumps(ANALYSIS))

    b = service(hang)
    b.job = ai.Job()
    threading.Timer(0.3, b.job.cancel.set).start()
    start = time.monotonic()
    with pytest.raises(ai.Cancelled):
        analyze(b)
    assert time.monotonic() - start < 3 and b.closed
    release.set()


def test_batches_are_announced_and_sized_for_an_agent():
    assert ai.ClaudeCliBackend.batch == 15
    messages = []

    def handler(request):
        prompt = json.loads(request.content)["prompt"]
        ids = [f"r{n}" for n in range(20) if f'id="r{n}"' in prompt]
        return reply(json.dumps({"result": json.dumps({"items": [{"rule_id": i, "assessment": "likely_ok", "why_manual": "w", "finding": "f", "evidence": []} for i in ids]})}))

    b = service(handler)
    b.job = ai.Job(notify=messages.append)
    reviews = ai.review(b, Digest(), [(f"r{n}", f"Requirement {n}.") for n in range(20)], ai.Usage())
    assert len(reviews) == 20 and any("items 16–20 of 20" in m for m in messages) and any(m.startswith("claude finished after") for m in messages)


def test_configuration(monkeypatch):
    for name in ("TERMINAL_URL", "TERMINAL_TOKEN", "LLM_MODEL", "LLM_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    assert ai.provider() == "claude-cli" and not ai.configured()
    monkeypatch.setenv("TERMINAL_URL", "http://terminal:8002")
    monkeypatch.setenv("TERMINAL_TOKEN", "tok")
    assert ai.configured() and ai.model_name() == "account default" and "Claude" in ai.endpoint_host()
    made = ai.make_client(repo="42/ps")
    assert isinstance(made, ai.ClaudeCliBackend) and made.repo == "42/ps" and made.model == ""
    monkeypatch.setenv("LLM_MODEL", "sonnet")
    assert ai.make_client(repo="x").model == "sonnet"
