"""The life of a session: created, read, deleted, and kept consistent with what is on disk."""

from __future__ import annotations

from typing import Protocol

from verdict.core.errors import Conflict, NotFound
from verdict.sessions.context import ReviewContext
from verdict.sessions.store import Session, Store

BUSY = ("cloning", "running")


class VerdictDocument(Protocol):
    def write(self, session: Session) -> None: ...
    def ensure_current(self, session: Session) -> bool: ...


class SessionService:
    def __init__(self, store: Store, context: ReviewContext, document: VerdictDocument) -> None:
        self.store, self.context, self.document = store, context, document

    def create(self) -> Session:
        return self.store.create()

    def find(self, session_id: str) -> Session:
        try:
            return self.store.get(session_id)
        except KeyError:
            raise NotFound("unknown session") from None

    def read(self, session_id: str) -> Session:
        """A session as it is asked for: a review of another context is dropped, and the verdict.md of the project says what the app says."""
        session = self.find(session_id)
        if self.context.drop_stale(session):
            if session.results:
                self.document.write(session)
            self.store.save(session)
        self.document.ensure_current(session)
        return session

    def delete(self, session_id: str) -> None:
        self.find(session_id)
        self.store.delete(session_id)

    @staticmethod
    def ensure_idle(session: Session) -> None:
        if session.state in BUSY:
            raise Conflict(f"session is busy ({session.state})")
