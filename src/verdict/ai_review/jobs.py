"""The AI reviews that are running, one per session, so that one can be cancelled."""

from __future__ import annotations

import threading

from verdict.reviews import ai as ai_mod


class AiJobs:
    """Registry of running jobs (by session id)."""

    def __init__(self) -> None:
        self._jobs: dict[str, ai_mod.Job] = {}
        self._lock = threading.Lock()

    def add(self, session_id: str, job: ai_mod.Job) -> None:
        with self._lock:
            self._jobs[session_id] = job

    def cancel(self, session_id: str) -> bool:
        """Tell the job of a session to stop and forget it. True when there was one."""
        with self._lock:
            job = self._jobs.pop(session_id, None)
        if job:
            job.cancel.set()
        return job is not None

    def stop_listed(self, session_id: str) -> None:
        """Stop the job but keep it listed: its thread removes it when it ends."""
        with self._lock:
            job = self._jobs.get(session_id)
        if job:
            job.cancel.set()

    def discard(self, session_id: str, job: ai_mod.Job) -> None:
        with self._lock:
            if self._jobs.get(session_id) is job:
                del self._jobs[session_id]
