"""The report claude saved for a review: read it, delete it."""

from fastapi import APIRouter

from terminal.report.files import ReportFiles
from terminal.report.reader import ReportReader


def report_router(reader: ReportReader, files: ReportFiles) -> APIRouter:
    router = APIRouter()

    @router.get("/sessions/{sid}/report")
    def read_report(sid: str) -> dict:
        return reader.read(sid)

    @router.delete("/sessions/{sid}/report")
    def delete_report(sid: str) -> dict:
        """A new run starts without the last report."""
        return {"deleted": files.discard(sid)}

    return router
