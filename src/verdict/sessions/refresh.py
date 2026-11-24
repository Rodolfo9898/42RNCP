"""What has to be settled again after the repository or the subjects of a review changed."""

from __future__ import annotations

from typing import Protocol

from verdict.sessions.context import ReviewContext
from verdict.sessions.store import Session


class NormSync(Protocol):
    def sync(self, session: Session) -> None: ...


class ContextRefresher:
    """Attach or remove the Norm, and drop the reviews of the old context."""

    def __init__(self, norm: NormSync, context: ReviewContext) -> None:
        self.norm, self.context = norm, context

    def refresh(self, session: Session) -> None:
        self.norm.sync(session)
        self.context.drop_stale(session)
