"""When to ask an OpenAI-compatible server again, and how long to wait first."""

from __future__ import annotations

from verdict.reviews.ai.backends.openai_compatible.replies import Reply


class RetryPolicy:
    """Strategy: temporary failures (rate limit, overloaded server) are retried with growing pauses, capped."""

    STATUSES = (429, 500, 502, 503, 504)
    ATTEMPTS = 3
    MAX_WAIT = 30.0

    def again(self, status: int, attempt: int) -> bool:
        """Whether a reply with this `status` to attempt number `attempt` (from 0) is worth another try."""
        return status in self.STATUSES and attempt < self.ATTEMPTS - 1

    def wait(self, reply: Reply, attempt: int) -> float:
        try:
            requested = float(reply.headers.get("retry-after", ""))
        except ValueError:
            requested = 0.0
        floor = 15.0 * (attempt + 1) if reply.status == 429 else 2.0 * 3 ** attempt   # rate limits need longer pauses
        return min(max(requested, floor), self.MAX_WAIT)
