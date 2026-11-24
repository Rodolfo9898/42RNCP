"""What every AI backend is, and the cancellation they all share."""

from __future__ import annotations

import threading
from typing import Protocol

from pydantic import BaseModel

from verdict.reviews.ai.contract.errors import Cancelled
from verdict.reviews.ai.contract.run import Job, Usage


class Backend(Protocol):
    """Strategy: the interchangeable ways to ask a model a question and get an answer that matches `schema`."""

    model: str
    batch: int  # manual-review items per request
    job: Job

    def structured(self, system: str, digest_text: str, task: str, schema: type[BaseModel], usage: Usage) -> BaseModel: ...


class BaseBackend:
    """What the backends have in common: the job they report to, and blocking calls that a cancel request can interrupt."""

    job: Job

    def __init__(self) -> None:
        self.job = Job()

    def _check(self) -> None:
        if self.job.cancel.is_set():
            raise Cancelled("Cancelled.")

    def _cancellable(self, fn):
        """Run a blocking call so that a cancel request is noticed within a fraction of a second."""
        box: dict = {}

        def target() -> None:
            try:
                box["value"] = fn()
            except BaseException as exc:  # handed back to the caller's thread
                box["error"] = exc

        worker = threading.Thread(target=target, daemon=True)
        worker.start()
        while worker.is_alive():
            worker.join(0.25)
            self._check()  # the abandoned request finishes (or times out) on its own, unseen
        if "error" in box:
            raise box["error"]
        return box["value"]
