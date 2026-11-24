"""Everything of the previous run goes before the next one starts."""

from __future__ import annotations

from collections.abc import Callable

from verdict.core.models import AIState, ClaudeReport
from verdict.documents.verdict_file import VerdictFile
from verdict.sessions.store import Session, Store


class FreshStart:
    """claude's report, the AI review, the results, the suggestions and the verdict.md in the project: the next run is assessed anew."""

    def __init__(self, store: Store, terminal, document: VerdictFile, cancel_ai: Callable[[str], None]) -> None:
        self.store, self.terminal, self.document, self.cancel_ai = store, terminal, document, cancel_ai

    def reset(self, session: Session) -> None:
        self.cancel_ai(session.id)
        self.terminal.delete_report(session.id)            # (what claude saved for the last run must not come back: best effort)
        with self.store.lock:
            session.runs += 1                              # (a claude started before this run is now for another context)
            session.ai = AIState(job=session.ai.job + 1)
            session.claude_review = session.claude_review_at = ""
            session.claude = ClaudeReport()
            session.review_items = []
            session.review_context = ""
            session.results, session.improvements, session.readme = [], [], {}
        self.document.remove(session)
