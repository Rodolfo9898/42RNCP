"""The composition root of the terminal service: builds every collaborator from the settings and mounts the routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from sandbox.display.xvfb import VirtualDisplay
from terminal.api.auth import TokenGuard
from terminal.api.environment import environment_router
from terminal.api.health import health_router
from terminal.api.reports import report_router
from terminal.api.reviews import review_router
from terminal.api.subjects import subjects_router
from terminal.claude.command import ClaudeCommand
from terminal.claude.headless import HeadlessReview
from terminal.environment.child import ChildEnvironment
from terminal.environment.selftest import EnvironmentSelfTest
from terminal.projects.folders import ProjectFolders
from terminal.projects.sanitizer import SanitizedCopy
from terminal.report.files import ReportFiles
from terminal.report.reader import ReportReader
from terminal.settings.settings import Settings
from terminal.subjects.intake import SubjectIntake
from terminal.subjects.store import SubjectStore


def create_app(settings: Settings, display: VirtualDisplay) -> FastAPI:
    """The service the web app's TerminalGateway talks to. Every route but /health needs the token (one dependency for all of them)."""
    folders = settings.folders
    command = ClaudeCommand(settings.claude)
    environment = ChildEnvironment(settings, display)
    reports = ReportFiles(folders)
    review = HeadlessReview(command, environment, ProjectFolders(settings.projects), SanitizedCopy(settings, environment),
                            settings.limits.review_timeout)
    selftest = EnvironmentSelfTest(environment, settings.scratch, [("gdb", ["gdb", "--version"], False), ("claude", command.version(), True)])

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        display.stop()

    app = FastAPI(title="verdict-terminal", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)   # (only the routes of the table)
    app.include_router(health_router(settings))
    guarded = [Depends(TokenGuard(settings.token))]
    app.include_router(report_router(ReportReader(reports, settings.limits), reports), dependencies=guarded)
    app.include_router(subjects_router(folders, SubjectStore(folders, settings.limits, reports.started), SubjectIntake(settings.limits)),
                       dependencies=guarded)
    app.include_router(environment_router(selftest), dependencies=guarded)
    app.include_router(review_router(review), dependencies=guarded)
    return app
