"""The composition root of the scraper service: builds every collaborator from the settings and mounts the routes."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, FastAPI

from scraper.jobs.runner import DownloadRunner
from scraper.server.auth import TokenGuard
from scraper.server.downloads import DownloadService, downloads_router
from scraper.server.errors import install_error_handlers
from scraper.server.health import health_router
from scraper.server.plan import PlanService, plan_router
from scraper.server.reorganizations import ReorganizationService, reorganizations_router
from scraper.server.sessions import SavedSessions
from scraper.server.settings import ServiceSettings
from scraper.server.workspace import Workspace
from scraper.site.http import HttpClient


def create_app(settings: ServiceSettings, *, http_factory: Callable[[], HttpClient] | None = None,
               runner: DownloadRunner | None = None) -> FastAPI:
    """The service the web app's gateway talks to. Every route but /health needs the token (one dependency for all of them).
    `http_factory` and `runner` can be replaced (the tests do): how the intra is reached, and how a download gets to run."""
    workspace = Workspace(settings.scraper)
    sessions = SavedSessions(settings.scraper, http_factory)
    runner = runner or DownloadRunner()

    app = FastAPI(title="verdict-scraper", docs_url=None, redoc_url=None, openapi_url=None)       # (only the routes of the table)
    install_error_handlers(app)
    app.include_router(health_router())
    guarded = [Depends(TokenGuard(settings.token))]
    app.include_router(plan_router(PlanService(workspace, sessions)), dependencies=guarded)
    app.include_router(downloads_router(DownloadService(workspace, sessions, runner)), dependencies=guarded)
    app.include_router(reorganizations_router(ReorganizationService(workspace, runner)), dependencies=guarded)
    return app
