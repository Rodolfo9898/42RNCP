"""What a route needs: the app's container, and the session of its address."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from verdict.app.container import Container
from verdict.sessions.service import SessionService
from verdict.sessions.store import Session


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_session(session_id: str, container: ContainerDep) -> Session:
    return container.sessions.find(session_id)         # 404 when unknown


def get_idle_session(session: Annotated[Session, Depends(get_session)]) -> Session:
    SessionService.ensure_idle(session)                # 409 while cloning or running
    return session


SessionDep = Annotated[Session, Depends(get_session)]
IdleSessionDep = Annotated[Session, Depends(get_idle_session)]
