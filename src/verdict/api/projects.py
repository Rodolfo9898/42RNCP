"""Which project a review is about: a repository to clone, or a folder that is already in the projects folder."""

from fastapi import APIRouter

from verdict.api.deps import ContainerDep, IdleSessionDep
from verdict.api.schemas import CloneSource, RepoSource
from verdict.sessions.view import SessionView

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects")
def projects(container: ContainerDep) -> dict:
    """The projects folder: where a clone can be placed, and what is there to review as it is."""
    return container.folders.listing()


@router.put("/sessions/{session_id}/repo")
def attach(source: RepoSource, session: IdleSessionDep, container: ContainerDep) -> dict:
    if isinstance(source, CloneSource):
        container.projects.clone(session, source.url, source.name, source.destination)
    else:
        container.projects.use_existing(session, source.path)
    return SessionView(session).to_dict()
