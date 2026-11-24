"""The JSON a client sees of a session: what the review has, in the shape the editor extension reads."""

from __future__ import annotations

from verdict.reports.report import corrected, summarize
from verdict.sessions.store import Session


def chosen_improvements(session: Session) -> list:
    """claude's own improvements replace the script heuristics once its report has been merged (one list, no duplicates)."""
    return session.claude.improvements if session.claude.structured and session.claude.improvements else session.improvements


class SessionView:
    """Presenter: one session, as a dict (the same keys whichever way it is asked for)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def to_dict(self) -> dict:
        s = self.session
        return {
            "id": s.id, "state": s.state, "message": s.message,
            "repo": s.repo.model_dump() if s.repo else None,
            "subjects": self._subjects(),
            "results": [r.model_dump() for r in corrected(s.results, s.claude)],
            "improvements": [i.model_dump() for i in chosen_improvements(s)],
            "claude": s.claude.model_dump(), "readme": s.readme, "verdict_file": s.verdict_file,
            "claude_review_at": s.claude_review_at, "ai": s.ai.model_dump(),
            "summary": summarize(s.results, s.ai, s.claude),
        }

    def _subjects(self) -> list[dict]:
        return [{"name": s.name, "kind": s.kind, "track": s.track, "lang": s.lang, "pages": s.pages,
                 "rules": [r.model_dump() for r in s.rules]} for s in self.session.subjects.values()]
