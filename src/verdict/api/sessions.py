"""A review: created, read, deleted."""

from fastapi import APIRouter, Response

from verdict.api.deps import ContainerDep
from verdict.sessions.view import SessionView

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201)
def create(container: ContainerDep) -> dict:
    return SessionView(container.sessions.create()).to_dict()


@router.get("/{session_id}")
def read(session_id: str, container: ContainerDep) -> dict:
    return SessionView(container.sessions.read(session_id)).to_dict()


@router.delete("/{session_id}", status_code=204)
def delete(session_id: str, container: ContainerDep) -> Response:
    container.sessions.delete(session_id)
    return Response(status_code=204)
