"""▶ Run checks: the pipeline that turns a project and its subjects into results and a verdict."""

from __future__ import annotations

from pathlib import Path

from verdict.checks import Ctx, run_checks
from verdict.core.background import Spawn, in_thread
from verdict.core.errors import VerdictError
from verdict.core.models import CheckResult
from verdict.documents.verdict_file import VerdictFile
from verdict.library.files import SubjectFiles
from verdict.library.subjects import SubjectService
from verdict.projects.folders import ProjectFolders
from verdict.reports import improve as improve_mod
from verdict.runs.fresh import FreshStart
from verdict.runs.network import NetworkSteps
from verdict.runs.workcopy import WorkCopy
from verdict.sessions.refresh import ContextRefresher
from verdict.sessions.service import SessionService
from verdict.sessions.store import Session, Store


class RunService:
    """Template Method: start() checks the session can run and begins afresh, execute() takes the same steps every time."""

    def __init__(self, store: Store, folders: ProjectFolders, subjects: SubjectService, files: SubjectFiles, sandbox,
                 network: NetworkSteps, workcopy: WorkCopy, fresh: FreshStart, refresher: ContextRefresher, document: VerdictFile,
                 spawn: Spawn = in_thread) -> None:
        self.store, self.folders, self.subjects, self.files, self.sandbox = store, folders, subjects, files, sandbox
        self.network, self.workcopy, self.fresh, self.refresher, self.document = network, workcopy, fresh, refresher, document
        self.spawn = spawn

    def start(self, session: Session) -> None:
        SessionService.ensure_idle(session)
        if not session.repo:
            raise VerdictError("clone a repository first")
        if not any(s.kind == "subject" for s in session.subjects.values()):
            raise VerdictError("add at least one subject PDF first")
        self.subjects.refresh_rules(session)                # (so a better parser applies at once, not only to subjects added from now on)
        self.refresher.refresh(session)
        self.fresh.reset(session)                           # every run starts from nothing: claude, its report, the AI review, the old verdict
        session.state, session.message = "running", "git pull…" if session.repo.url else ""
        self.store.save(session)
        self.spawn(self.execute, session)

    def execute(self, session: Session) -> None:
        try:
            session.message = self.network.pull(session)    # (what the pull did; the status bar keeps saying it)
            clone = self._clone_of(session)
        except Exception as exc:
            self._fail(session, exc)
            return
        work: Path | None = None
        try:
            work = self.workcopy.make(session, clone)
            self._run_checks(session, clone, work)
            session.state = "done"
        except Exception as exc:
            self._fail(session, exc)
        finally:
            if work is not None:
                self.workcopy.remove(work)
        self.store.save(session)

    def _clone_of(self, session: Session) -> Path:
        folder = self.folders.of(session)
        if folder is None:
            raise VerdictError("the project folder of this review is not available")
        return folder.resolve()

    def _run_checks(self, session: Session, clone: Path, work: Path) -> None:
        subjects = self.files.sync(session)
        notes = self.network.download_submodules(session, work)
        sandbox = self.sandbox.with_env({"SUBJECTS_DIR": str(subjects)}) if self.sandbox else None
        run_checks(Ctx(repo=work.resolve(), rules=session.rules(), lang=session.lang(), cache={"submodule_notes": notes}, sandbox=sandbox),
                   lambda result: self._emit(session, result))
        # Suggestions and the README look at what was committed, not at what building left behind.
        pristine = Ctx(repo=clone, rules=session.rules(), sandbox=None, lang=session.lang())
        session.improvements = improve_mod.suggest(pristine)
        session.readme = improve_mod.readme_status(pristine)
        self.document.write(session)

    def _emit(self, session: Session, result: CheckResult) -> None:
        with self.store.lock:
            session.results.append(result)

    def _fail(self, session: Session, exc: Exception) -> None:
        session.state, session.message = "error", f"{type(exc).__name__}: {exc}"
        self.store.save(session)
