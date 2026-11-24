"""What a review is about, and when what was said about it no longer applies."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable

from verdict.core.models import AIState, ClaudeReport
from verdict.sessions.store import Session


class ReviewContext:
    """The cloned commit, the subjects and the run a review follows. A review made for another context is stale."""

    def __init__(self, lock: threading.RLock, on_drop: Callable[[str], None] = lambda session_id: None) -> None:
        self.lock = lock
        self.on_drop = on_drop                      # called with the session id: a running AI review of the old context is cancelled

    def of(self, session: Session) -> str:
        repo = session.repo
        subjects = sorted(name for name, s in session.subjects.items() if s.kind == "subject")
        return json.dumps([[repo.url, repo.path, repo.commit] if repo else None, subjects, session.runs])

    def drop_stale(self, session: Session) -> bool:
        """Forget claude's review and the AI review when they were made for another repository, commit or set of subjects
        (e.g. libft's review must never show up in the verdict of the next project). True when something was dropped."""
        has_reviews = session.claude_review or session.review_items or session.ai.state != "idle" or session.ai.reviews
        if not has_reviews or session.review_context == self.of(session):
            return False
        self.on_drop(session.id)
        with self.lock:
            session.ai = AIState(job=session.ai.job + 1)
            session.claude_review = session.claude_review_at = ""
            session.claude = ClaudeReport()
            session.review_items = []
            session.review_context = ""
        return True
