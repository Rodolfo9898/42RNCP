"""GET /plan: what the library holds and what is missing, per track, and whether the saved session would let a download start."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from scraper.inventory.builder import PlanReportBuilder
from scraper.server.sessions import SavedSessions
from scraper.server.workspace import Workspace


class PlanService:
    """The PlanReport of a selection (offline), told together with the session's status (the one network question)."""

    def __init__(self, workspace: Workspace, sessions: SavedSessions) -> None:
        self.workspace, self.sessions = workspace, sessions

    def answer(self, tracks: list[str] | None, children: bool) -> dict:
        selection = self.workspace.select(tracks=tracks, children=children)
        report = PlanReportBuilder(selection.plan, self.workspace.catalog, self.workspace.library, selection.settings).build(selection.targets)
        return {
            "session": asdict(self.sessions.status()),
            "tracks": [{"track": t.track, "label": t.label, "total": t.total, "with_pdf": t.with_pdf,
                        "missing": [asdict(m) for m in t.missing]} for t in report.tracks],
            "unknown": report.unknown,
            "misplaced": report.misplaced,
        }


def plan_router(service: PlanService) -> APIRouter:
    router = APIRouter()

    @router.get("/plan")
    def plan(track: list[str] | None = Query(default=None), children: bool = True) -> dict:
        return service.answer(track, children)

    return router
