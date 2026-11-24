"""The Anthropic API as a backend."""

from __future__ import annotations

import time

from verdict.reviews.ai.backends.anthropic_api.failures import API_ERRORS, explain, usable_answer
from verdict.reviews.ai.contract import BaseBackend

MAX_TOKENS = 16000


class AnthropicBackend(BaseBackend):
    """Strategy: asks the Anthropic API, which constrains the answer to the schema itself."""

    batch = 20

    def __init__(self, client, model: str):
        super().__init__()
        self.client, self.model = client, model

    def structured(self, system, digest_text, task, schema, usage):
        self._check()
        self.job.notify(f"Asking {self.model}… waiting for its answer")
        started = time.monotonic()
        try:
            response = self._cancellable(lambda: self.client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": [
                    # The repository digest is identical across calls, so the second call reads it from the cache.
                    {"type": "text", "text": digest_text, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": task},
                ]}],
                output_format=schema,
            ))
        except API_ERRORS as exc:
            raise explain(exc, self.model) from exc
        usage.add(response.usage)
        self.job.notify(f"Answer received after {time.monotonic() - started:.0f}s ({response.usage.output_tokens or 0:,} tokens written)")
        return usable_answer(response)
