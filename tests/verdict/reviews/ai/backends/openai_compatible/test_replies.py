import json

import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.backends.openai_compatible.fakes import ANALYSIS, KEY, backend, completion, reply, run_analysis


# ---------------------------------------------------------------- odd but real-world reply shapes


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
