import json
import time

import httpx
import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.backends.openai_compatible.fakes import ANALYSIS, backend, completion, run_analysis


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
    monkeypatch.setattr(time, "monotonic", lambda: next(clock, 9.0))
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
