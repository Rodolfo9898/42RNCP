"""The subject PDFs of a review: which ones are held, hand them over."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from terminal.settings.folders import SessionFolders
from terminal.subjects.intake import SubjectIntake, SubjectRefused
from terminal.subjects.store import SubjectStore


def subjects_router(folders: SessionFolders, store: SubjectStore, intake: SubjectIntake) -> APIRouter:
    router = APIRouter()

    @router.get("/sessions/{sid}/subjects")
    def list_subjects(sid: str) -> dict:
        """The PDFs held for a review, with their hashes, so the web app only sends what is missing or different."""
        return {"files": store.digests(sid)}

    @router.put("/sessions/{sid}/subjects")
    async def store_subjects(sid: str, files: list[UploadFile] = File(...)) -> dict:
        """Replace the PDFs of a review with exactly these. Read-only for whatever runs here."""
        if not folders.is_valid(sid):
            raise HTTPException(400, "bad session id")
        try:
            received = await intake.collect(files)
        except SubjectRefused as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            store.replace(sid, received)
        except OSError as exc:
            raise HTTPException(500, f"could not store the PDFs: {exc}") from exc
        return {"stored": sorted(received)}

    return router
