"""claude's review, merged into the verdict: picked up from the terminal after each pass, or forced."""

from __future__ import annotations

from datetime import datetime, timezone

from verdict.core.errors import NotFound, Unavailable, VerdictError
from verdict.documents.verdict_file import VerdictFile
from verdict.projects.folders import ProjectFolders
from verdict.reviews.claude_report import parse_report
from verdict.reviews.digest import line_index
from verdict.sessions.context import ReviewContext
from verdict.sessions.store import Session, Store

NOT_SAVED = "claude has not saved its report yet. Ask it to save it as claude-review.md and approve the write, then try again."
NO_VERDICT_FILE = ("The review was stored, but verdict.md could not be written into the repository (files of that name exist there "
                   "and are not ours, or they are links).")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClaudeReviewService:
    def __init__(self, store: Store, terminal, folders: ProjectFolders, context: ReviewContext, document: VerdictFile) -> None:
        self.store, self.terminal, self.folders, self.context, self.document = store, terminal, folders, context, document

    def sync(self, session: Session, force: bool = False) -> dict:
        """The editor asks after each pass of claude's review (`force` false: only a report this review asked for counts, `stale` says
        it is for something else) or when you merge by hand (`force`: whatever claude saved is adopted for the project as it is now)."""
        return self.merge(session) if force else self._pick_up(session)

    def collect(self, session: Session, context: str | None = None, strict: bool = False) -> bool:
        """Store claude's saved report in the session and merge it into verdict.md. False when there was nothing new.
        `context` is what the report was asked for: one for another repository or subject set is ignored. `strict`: a terminal
        service that cannot be reached raises instead of counting as "nothing new"."""
        if context is not None and context != self.context.of(session):
            return False
        try:
            text = self._saved_text(session)
        except Exception as exc:
            if strict:
                raise Unavailable("could not reach the terminal service") from exc
            return False
        if text and text != session.claude_review:
            self._adopt(session, text)
            return True
        return self.document.ensure_current(session)

    def apply(self, session: Session) -> None:
        """Turn the structured block at the end of claude's report into assessments, corrections, improvements and a verdict."""
        root = self.folders.of(session)
        files = line_index(root) if root is not None else {}
        earlier = {k: v for k, v in session.ai.reviews.items() if v.by == "Claude"}
        report, reviews = parse_report(session.claude_review, session.review_items, files, previous=session.claude, previous_reviews=earlier)
        with self.store.lock:
            if not report.structured and session.claude.structured:      # a report it could not read must not undo the one it could
                session.claude.problems = report.problems
            else:
                kept = {k: v for k, v in session.ai.reviews.items() if v.by != "Claude"}
                session.ai.reviews = {**kept, **reviews}
                session.claude = report
            session.review_context = self.context.of(session)

    def merge(self, session: Session) -> dict:
        """Force claude's saved report into the session and into verdict.md, whatever happened before. Says why when there is nothing."""
        if not session.results:
            raise VerdictError("run the checks first")
        try:
            data = self.terminal.report(session.id)
        except Exception as exc:
            raise Unavailable("could not reach the terminal service") from exc
        text = data["text"] if data.get("found") else ""
        if not text.strip():
            raise NotFound(NOT_SAVED)
        changed = text != session.claude_review
        if changed:
            with self.store.lock:
                session.claude_review, session.claude_review_at = text, now()
        if changed or not session.claude.structured:
            self.apply(session)                    # (also re-reads a report stored before the numbering existed)
        self.document.write(session)               # always: an unchanged report must still be written if the file is missing
        self.store.save(session)
        return self._answer(session, new=changed, written=bool(session.verdict_file), stale=False,
                            source=data.get("name") or "claude-review.md")

    def _pick_up(self, session: Session) -> dict:
        before = session.claude_review
        written = self.collect(session, session.review_context, strict=True)
        return self._answer(session, new=session.claude_review != before, written=written,
                            stale=session.review_context != self.context.of(session))

    def _saved_text(self, session: Session) -> str | None:
        data = self.terminal.report(session.id)
        return data["text"] if data.get("found") and data["text"].strip() else None

    def _adopt(self, session: Session, text: str) -> None:
        with self.store.lock:
            session.claude_review, session.claude_review_at = text, now()
        self.apply(session)
        self.document.write(session)
        self.store.save(session)

    @staticmethod
    def _answer(session: Session, *, new: bool, written: bool, stale: bool, source: str = "") -> dict:
        return {"new": new, "written": written, "stale": stale, "verdict_file": session.verdict_file,
                "structured": session.claude.structured, "assessed": session.claude.assessed, "total": session.claude.total,
                "problems": session.claude.problems, "source_name": source,
                "warning": "" if session.verdict_file or not session.claude_review else NO_VERDICT_FILE}
