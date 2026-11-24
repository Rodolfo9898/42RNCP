import json

import httpx
import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.backends.openai_compatible.fakes import ANALYSIS, KEY, backend, completion, run_analysis


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
