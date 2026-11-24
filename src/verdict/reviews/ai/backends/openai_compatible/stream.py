"""Reading a streamed (server-sent events) answer."""

from __future__ import annotations

import json
import time
from collections.abc import Callable

import httpx

from verdict.reviews.ai.backends.openai_compatible.replies import Reply

REPORT_EVERY = 3     # seconds between two "receiving the answer" notes


class StreamReader:
    """Assembles the chunks of a streamed answer into the one-piece reply the rest of the backend understands."""

    def __init__(self, model: str, check: Callable[[], None], notify: Callable[[str], None]):
        self.model, self.check, self.notify = model, check, notify
        self.content: list[str] = []
        self.reasoning: list[str] = []
        self.finish: str | None = None
        self.counts: dict = {}

    def read(self, response: httpx.Response) -> Reply:
        last_report, started = time.monotonic(), time.monotonic()
        for line in response.iter_lines():
            self.check()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            chunk = self._chunk(payload)
            if chunk is None:
                continue
            if chunk.get("error"):
                return Reply(200, response.headers, {"error": chunk["error"]})
            self._absorb(chunk)
            if time.monotonic() - last_report >= REPORT_EVERY:
                last_report = time.monotonic()
                self._report(last_report - started)
        message = {"content": "".join(self.content) or None, "reasoning_content": "".join(self.reasoning) or None}
        return Reply(200, response.headers, {"choices": [{"message": message, "finish_reason": self.finish}], "usage": self.counts})

    @staticmethod
    def _chunk(payload: str) -> dict | None:
        try:
            chunk = json.loads(payload)
        except ValueError:
            return None
        return chunk if isinstance(chunk, dict) else None

    def _absorb(self, chunk: dict) -> None:
        self.counts = chunk.get("usage") or self.counts
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                self.content.append(delta["content"])
            if delta.get("reasoning_content") or delta.get("reasoning"):
                self.reasoning.append(delta.get("reasoning_content") or delta.get("reasoning"))
            self.finish = choice.get("finish_reason") or self.finish

    def _report(self, seconds: float) -> None:
        written, thought = sum(map(len, self.content)), sum(map(len, self.reasoning))
        self.notify(f"Receiving the answer from {self.model}: {written:,} characters written"
                    + (f", {thought:,} characters of reasoning" if thought else "") + f" ({seconds:.0f}s)")
