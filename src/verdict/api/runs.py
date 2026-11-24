"""▶ Run checks."""

from fastapi import APIRouter

from verdict.api.deps import ContainerDep, SessionDep
from verdict.sessions.view import SessionView

router = APIRouter(prefix="/api/sessions/{session_id}/runs", tags=["runs"])


@router.post("", status_code=202)
def start(session: SessionDep, container: ContainerDep) -> dict:
    container.runs.start(session)
    return SessionView(session).to_dict()
