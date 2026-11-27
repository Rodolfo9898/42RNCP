"""Reading what `claude -p` printed, which comes in more shapes than its documentation admits."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from verdict.reviews.ai.contract import AIError, Usage, clean, extract_json

NOT_SIGNED_IN = re.compile(r"/login|not logged in|please run .*login|invalid api key|authentication", re.I)
COUNTED_INPUT = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


class ClaudeOutput:
    """The answer of the terminal service to a review: claude's stdout and stderr, and how it exited."""

    def __init__(self, reply: dict, usage: Usage):
        self.reply, self.usage = reply, usage
        self.stdout, self.stderr = reply.get("stdout", ""), reply.get("stderr", "")

    def parse(self, schema: type[BaseModel]) -> BaseModel:
        """The answer as `schema`, or an AIError saying what claude said instead."""
        if NOT_SIGNED_IN.search(f"{self.stdout}\n{self.stderr}"):
            raise AIError("claude is not signed in inside the terminal container. Open the Terminal tab, run claude and use /login once. "
                          "(On a Mac claude uses your Apple sign-in instead: stop the app and run `make run` again, it checks that sign-in.)")
        try:
            outer = json.loads(self.stdout)
        except ValueError:
            outer = None
        candidates = self._candidates(outer)
        if outer is None:
            candidates.append(self.stdout)
        for candidate in candidates:
            validated = self._validated(candidate, schema)
            if validated is not None:
                return validated
        if self.reply.get("returncode") not in (0, None):
            raise AIError(f"claude exited with an error: {clean(self.stderr or self.stdout, 200) or self.reply.get('returncode')}")
        raise AIError("claude answered, but not in the expected JSON format. Try again.")

    def _candidates(self, outer) -> list:
        """Where the answer may be, best guess first, counting what the run cost on the way."""
        results: list = []
        if isinstance(outer, list):
            results = [item for item in outer if isinstance(item, dict) and item.get("type") == "result"][-1:]
        elif isinstance(outer, dict):
            results = [outer]
        candidates: list = []
        for item in results:
            self._count(item.get("usage") or {})
            if item.get("is_error"):
                raise AIError("claude reported an error: " + clean(str(item.get("result") or item.get("subtype") or "unknown"), 200))
            candidates += [item.get("structured_output"), item.get("result"), item.get("response"), item]
        return candidates

    def _count(self, counts: dict) -> None:
        self.usage.input_tokens += sum(int(counts.get(k) or 0) for k in COUNTED_INPUT)
        self.usage.output_tokens += int(counts.get("output_tokens") or 0)

    @staticmethod
    def _validated(candidate, schema: type[BaseModel]) -> BaseModel | None:
        if candidate is None:
            return None
        try:
            payload = candidate if isinstance(candidate, dict) else json.loads(extract_json(str(candidate)))
            return schema.model_validate(payload)
        except (ValidationError, ValueError, TypeError):
            return None
