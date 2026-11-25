"""POST /downloads, GET and DELETE /downloads/current: start a download, follow it, stop it."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Query

from scraper.cli.commands import ScrapeCommand
from scraper.core.debug import NullDumper
from scraper.core.exceptions import ScraperError
from scraper.core.reporting import Reporter
from scraper.jobs.job import CommandFactory
from scraper.jobs.runner import AlreadyRunning, DownloadRunner
from scraper.jobs.state import JobState
from scraper.server.schemas import DownloadRequest
from scraper.server.sessions import SavedSessions
from scraper.server.workspace import Selection, Workspace


class DownloadService:
    """Starts the download of a selection when the saved session works, and hands out the state of the current one."""

    def __init__(self, workspace: Workspace, sessions: SavedSessions, runner: DownloadRunner) -> None:
        self.workspace, self.sessions, self.runner = workspace, sessions, runner

    def start(self, request: DownloadRequest) -> dict:
        if self.runner.running:                       # (the runner checks again when it starts: this saves the network round trip)
            raise AlreadyRunning("a download is already running: stop it or wait for it to finish")
        selection = self.workspace.select(tracks=request.tracks, projects=request.projects, children=request.children,
                                          artifacts=request.artifacts)
        status = self.sessions.status()
        if not status.valid:                          # said now, not from a background thread nobody is watching
            raise ScraperError(status.advice())
        job = self.runner.start(self._command_factory(selection, request.force))
        return {"id": job.id, "state": JobState.RUNNING.value}

    def current(self, since: int) -> dict:
        snapshot = self.runner.snapshot(since)
        return {"state": snapshot.state.value, "id": snapshot.id, "lines": snapshot.lines, "next": snapshot.next,
                "summary": asdict(snapshot.summary) if snapshot.summary else None}

    def cancel(self) -> dict:
        return {"state": self.runner.cancel().value}

    def _command_factory(self, selection: Selection, force: bool) -> CommandFactory:
        def make(reporter: Reporter, cancelled) -> ScrapeCommand:
            return ScrapeCommand(targets=selection.targets, settings=selection.settings, session=self.sessions.manager(reporter),
                                 library=self.workspace.library, reporter=reporter, dumper=NullDumper(), force=force, cancelled=cancelled)
        return make


def downloads_router(service: DownloadService) -> APIRouter:
    router = APIRouter()

    @router.post("/downloads", status_code=202)
    def start(request: DownloadRequest = Body(default_factory=DownloadRequest)) -> dict:
        return service.start(request)

    @router.get("/downloads/current")
    def current(since: int = Query(default=0, ge=0)) -> dict:
        return service.current(since)

    @router.delete("/downloads/current")
    def cancel() -> dict:
        return service.cancel()

    return router
