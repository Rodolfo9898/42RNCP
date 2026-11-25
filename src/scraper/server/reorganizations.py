"""POST /reorganizations: file the PDFs and artifacts you have in the folders of their series (or only say what would move)."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Body

from scraper.jobs.runner import AlreadyRunning, DownloadRunner
from scraper.server.schemas import ReorganizationRequest
from scraper.server.workspace import Workspace
from scraper.storage.reorganize import Reorganizer


class ReorganizationService:
    """One reorganization at a time, and none while a download writes into the same folders."""

    def __init__(self, workspace: Workspace, runner: DownloadRunner) -> None:
        self.workspace, self.runner = workspace, runner
        self._lock = threading.Lock()

    def run(self, dry_run: bool) -> dict:
        if self.runner.running:
            raise AlreadyRunning("a download is running: stop it or wait for it to finish before filing the files")
        library = self.workspace.library
        reorganizer = Reorganizer(library)
        with self._lock:
            moves = reorganizer.moves(self.workspace.select().targets)
            done = [] if dry_run else reorganizer.apply(moves)
        return {"dry_run": dry_run, "done": len(done),
                "moves": [{"from": library.shown(m.source), "to": library.shown(m.destination)} for m in moves]}


def reorganizations_router(service: ReorganizationService) -> APIRouter:
    router = APIRouter()

    @router.post("/reorganizations")
    def reorganize(request: ReorganizationRequest = Body(default_factory=ReorganizationRequest)) -> dict:
        return service.run(request.dry_run)

    return router
