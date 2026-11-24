import httpx

from verdict.reviews.ai.backends.openai_compatible.retry import RetryPolicy
from verdict.reviews.ai.backends.openai_compatible.replies import Reply


def reply(status, **headers):
    return Reply(status, httpx.Headers(headers), None)


def test_only_temporary_failures_are_tried_again_and_never_after_the_last_attempt():
    policy = RetryPolicy()
    assert [policy.again(status, 0) for status in (429, 500, 502, 503, 504)] == [True] * 5
    assert not any(policy.again(status, 0) for status in (200, 400, 401, 402, 403, 404))
    assert policy.again(503, RetryPolicy.ATTEMPTS - 2) and not policy.again(503, RetryPolicy.ATTEMPTS - 1)


def test_the_pauses_grow_and_a_rate_limit_waits_longer_but_never_beyond_the_cap():
    policy = RetryPolicy()
    assert [policy.wait(reply(503), attempt) for attempt in (0, 1, 2)] == [2.0, 6.0, 18.0]
    assert [policy.wait(reply(429), attempt) for attempt in (0, 1)] == [15.0, 30.0]
    assert policy.wait(reply(503, **{"retry-after": "10"}), 0) == 10.0 and policy.wait(reply(503, **{"retry-after": "3600"}), 0) == RetryPolicy.MAX_WAIT
    assert policy.wait(reply(503, **{"retry-after": "soon"}), 0) == 2.0
