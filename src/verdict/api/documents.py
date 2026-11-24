"""What the review writes: the verdict, and the row of the project in Progress.md."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from verdict.api.deps import ContainerDep, SessionDep

router = APIRouter(prefix="/api/sessions/{session_id}", tags=["documents"])


@router.get("/verdict.md", response_class=PlainTextResponse)
def verdict(session: SessionDep, container: ContainerDep, download: bool = False) -> PlainTextResponse:
    headers = {"Content-Disposition": 'attachment; filename="verdict.md"'} if download else {}
    return PlainTextResponse(container.document.text(session), media_type="text/markdown; charset=utf-8", headers=headers)


@router.put("/progress")
def progress(session: SessionDep, container: ContainerDep) -> dict:
    """Record the result the verdict shows now in the project's row: pressed once you accept it, never by itself."""
    return container.progress.record(session)
