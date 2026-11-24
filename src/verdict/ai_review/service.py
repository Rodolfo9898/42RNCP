"""The AI review through an API (or the Claude CLI service): started, followed and cancelled."""

from __future__ import annotations

from verdict.ai_review.jobs import AiJobs
from verdict.ai_review.runner import AiProgress, AiReviewRun, now
from verdict.core.background import Spawn, in_thread
from verdict.core.errors import Conflict, VerdictError
from verdict.core.models import AIEvent, AIState
from verdict.documents.verdict_file import VerdictFile
from verdict.projects.folders import ProjectFolders
from verdict.reviews import ai as ai_mod
from verdict.sessions.context import ReviewContext
from verdict.sessions.service import BUSY
from verdict.sessions.store import Session, Store

NOT_CONFIGURED = ("The AI review is not configured. Set ANTHROPIC_API_KEY, or LLM_BASE_URL + LLM_API_KEY + LLM_MODEL, in .env "
                  "(see the README).")


class AiReviewService:
    def __init__(self, store: Store, folders: ProjectFolders, context: ReviewContext, document: VerdictFile, jobs: AiJobs,
                 spawn: Spawn = in_thread) -> None:
        self.store, self.folders, self.context, self.document, self.jobs, self.spawn = store, folders, context, document, jobs, spawn

    def start(self, session: Session) -> None:
        if not ai_mod.configured():
            raise VerdictError(NOT_CONFIGURED)
        if session.state in BUSY or session.ai.state == "running":
            raise Conflict("something is already running")
        if not session.results or self.folders.of(session) is None:
            raise VerdictError("run the checks first")
        state = AIState(state="running", model=ai_mod.model_name(), started_at=now(), job=session.ai.job + 1)
        session.ai = state
        session.review_context = self.context.of(session)
        progress = AiProgress(self.store, session, state)
        job = ai_mod.Job(notify=progress.note)
        self.jobs.add(session.id, job)
        progress.note(f"Starting the AI review with {state.model} via {ai_mod.endpoint_host()}")
        self.spawn(AiReviewRun(self.store, self.folders, self.document, self.jobs, session, state, job).run)

    def cancel(self, session: Session) -> None:
        state = session.ai
        with self.store.lock:
            if state.state == "running":
                state.progress.append(AIEvent(at=now(), text="Stopped by you"))
                state.state, state.message, state.step = "cancelled", "Stopped by you.", ""
                self.jobs.stop_listed(session.id)
        self.store.save(session)
