"""The requests for claude: the review of what the checks did not cover, and the fixes of what the review found."""

from __future__ import annotations

from shared.constants import TERMINAL_REPORTS_ROOT, TERMINAL_SUBJECTS_ROOT
from verdict.core.errors import VerdictError
from verdict.library.handover import SubjectHandover
from verdict.projects.folders import ProjectFolders
from verdict.repository import repo as repo_mod
from verdict.reviews.prompts import build_fix_prompt, build_review_prompt, find_docker_files, manual_items
from verdict.sessions.context import ReviewContext
from verdict.sessions.store import Session, Store


class PromptService:
    def __init__(self, store: Store, folders: ProjectFolders, context: ReviewContext, handover: SubjectHandover) -> None:
        self.store, self.folders, self.context, self.handover = store, folders, context, handover

    def review(self, session: Session) -> dict:
        """The review request for claude, built from what the checks did and did not cover. The subject PDFs go to the terminal
        container first, where the editor starts claude with this prompt."""
        text, stats = self._review_prompt(session)
        self.handover.push(session)
        return {"text": text, **stats}

    def fix(self, session: Session) -> dict:
        """A prompt that asks an AI to fix what the review found. `text` is empty when there is nothing to fix."""
        self._need_results(session)
        text, stats = build_fix_prompt(project=self._project(session), subjects=list(session.subjects), lang=session.lang(),
                                       results=session.results, ai=session.ai, claude=session.claude, rules=session.rules(),
                                       report_dir=f"{TERMINAL_REPORTS_ROOT}/{session.id}")
        return {"text": text, **stats}

    def _review_prompt(self, session: Session) -> tuple[str, dict]:
        self._need_results(session)
        session.review_items = manual_items(session.results)        # claude answers by these numbers
        session.review_context = self.context.of(session)
        self.store.save(session)
        root = self.folders.of(session)
        docker_files = find_docker_files(p.as_posix() for p in repo_mod.tracked_files(root)) if root else []
        return build_review_prompt(project=self._project(session), subjects=list(session.subjects), lang=session.lang(),
                                   results=session.results, docker_files=docker_files, rules=session.rules(),
                                   subjects_dir=f"{TERMINAL_SUBJECTS_ROOT}/{session.id}",
                                   report_dir=f"{TERMINAL_REPORTS_ROOT}/{session.id}")

    @staticmethod
    def _need_results(session: Session) -> None:
        if not session.results or session.repo is None:
            raise VerdictError("run the checks first")

    @staticmethod
    def _project(session: Session) -> str:
        return session.repo.name or session.repo.path
