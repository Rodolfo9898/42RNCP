"""The composition root: every service of the app, built once and wired to the ones it needs."""

from __future__ import annotations

from verdict.ai_review.jobs import AiJobs
from verdict.ai_review.service import AiReviewService
from verdict.app.settings import Settings
from verdict.claude_review.prompts import PromptService
from verdict.claude_review.service import ClaudeReviewService
from verdict.core.background import Spawn, in_thread
from verdict.documents.progress import ProgressService
from verdict.documents.verdict_file import VerdictFile
from verdict.gateways.sandbox import Sandbox
from verdict.gateways.scraper import NullScraper, ScraperGateway
from verdict.gateways.terminal import NullTerminal, TerminalGateway
from verdict.health.environment import EnvironmentService
from verdict.health.status import HealthService
from verdict.library.catalog import LibraryService
from verdict.library.downloads import SubjectDownloads
from verdict.library.files import SubjectFiles
from verdict.library.handover import SubjectHandover
from verdict.library.norm import NormAttachment
from verdict.library.pages import PageImages
from verdict.library.subjects import SubjectService
from verdict.projects.folders import ProjectFolders
from verdict.projects.service import ProjectService
from verdict.runs.fresh import FreshStart
from verdict.runs.network import NetworkSteps
from verdict.runs.service import RunService
from verdict.runs.workcopy import WorkCopy
from verdict.sessions.context import ReviewContext
from verdict.sessions.refresh import ContextRefresher
from verdict.sessions.service import SessionService
from verdict.sessions.store import Store

FROM_ENVIRONMENT = object()      # "the sandbox the environment names" (None means: no sandbox)


class Container:
    """What a test replaces is passed in (the sandbox, the terminal and scraper gateways, how background work is started); the rest is
    built here."""

    def __init__(self, settings: Settings, *, sandbox=FROM_ENVIRONMENT, terminal=None, scraper=None, spawn: Spawn = in_thread) -> None:
        self.settings = settings
        self.sandbox = Sandbox.from_env() if sandbox is FROM_ENVIRONMENT else sandbox
        self.terminal = terminal or (TerminalGateway(settings.terminal_url, settings.terminal_token) if settings.terminal_configured
                                     else NullTerminal())
        self.scraper = scraper or (ScraperGateway(settings.scraper_url, settings.scraper_token) if settings.scraper_configured
                                   else NullScraper())
        self.store = Store(settings.workspace)
        self._build_library()
        self._build_sessions()
        self._build_reviews(spawn)
        self._build_runs(spawn)
        self.health = HealthService(self.sandbox)
        self.environment = EnvironmentService(self.sandbox, self.terminal, settings.workspace)

    def _build_library(self) -> None:
        self.folders = ProjectFolders(self.settings.projects)
        self.library = LibraryService(self.settings.samples)
        self.files = SubjectFiles(self.store, self.library)
        self.norm = NormAttachment(self.library, self.folders)
        self.pages = PageImages(self.files)
        self.handover = SubjectHandover(self.files, self.terminal)
        self.downloads = SubjectDownloads(self.scraper)

    def _build_sessions(self) -> None:
        self.jobs = AiJobs()
        self.context = ReviewContext(self.store.lock, self.jobs.cancel)
        self.refresher = ContextRefresher(self.norm, self.context)
        self.document = VerdictFile(self.folders, self.store)
        self.sessions = SessionService(self.store, self.context, self.document)
        self.subjects = SubjectService(self.store, self.library, self.files, self.norm, self.refresher)
        self.projects = ProjectService(self.store, self.folders, self.refresher, self.settings.workspace / "known_hosts")

    def _build_reviews(self, spawn: Spawn) -> None:
        self.claude = ClaudeReviewService(self.store, self.terminal, self.folders, self.context, self.document)
        self.prompts = PromptService(self.store, self.folders, self.context, self.handover)
        self.ai = AiReviewService(self.store, self.folders, self.context, self.document, self.jobs, spawn)
        self.progress = ProgressService(self.settings.progress_file)

    def _build_runs(self, spawn: Spawn) -> None:
        network = NetworkSteps(self.folders, self.norm, self.settings.workspace / "known_hosts")
        fresh = FreshStart(self.store, self.terminal, self.document, self.jobs.cancel)
        self.runs = RunService(self.store, self.folders, self.subjects, self.files, self.sandbox, network,
                               WorkCopy(self.settings.workspace), fresh, self.refresher, self.document, spawn)
