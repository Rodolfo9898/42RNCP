"""The subjects of a review: the library PDFs it was given, and their pages."""

from fastapi import APIRouter, Response

from verdict.api.deps import ContainerDep, SessionDep
from verdict.api.schemas import SubjectPicks
from verdict.sessions.view import SessionView

router = APIRouter(prefix="/api/sessions/{session_id}/subjects", tags=["subjects"])


@router.post("")
def add(picks: SubjectPicks, session: SessionDep, container: ContainerDep) -> dict:
    container.subjects.add_from_library(session, picks.paths)
    return SessionView(session).to_dict()


@router.delete("/{name}")
def remove(name: str, session: SessionDep, container: ContainerDep) -> dict:
    container.subjects.remove(session, name)
    return SessionView(session).to_dict()


@router.get("/{name}/pages/{page}.png")
def page(name: str, page: int, session: SessionDep, container: ContainerDep) -> Response:
    """One page of a subject PDF as an image (the editor shows images, it does not embed a PDF viewer)."""
    return Response(container.pages.png(session, name, page), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})
