"""The reviews of a project: claude's, the one done through an API, and the prompts that start them."""

from fastapi import APIRouter

from verdict.api.deps import ContainerDep, SessionDep
from verdict.api.schemas import ClaudeReviewRequest
from verdict.sessions.view import SessionView

router = APIRouter(prefix="/api/sessions/{session_id}", tags=["reviews"])


@router.put("/claude-review")
def sync_claude(request: ClaudeReviewRequest, session: SessionDep, container: ContainerDep) -> dict:
    """Merge what claude saved into the verdict: after each pass (the editor asks), or forced."""
    return container.claude.sync(session, request.force)


@router.post("/ai-review", status_code=202)
def start_ai(session: SessionDep, container: ContainerDep) -> dict:
    container.ai.start(session)
    return SessionView(session).to_dict()


@router.delete("/ai-review")
def cancel_ai(session: SessionDep, container: ContainerDep) -> dict:
    container.ai.cancel(session)
    return SessionView(session).to_dict()


@router.get("/prompts/review")
def review_prompt(session: SessionDep, container: ContainerDep) -> dict:
    return container.prompts.review(session)


@router.get("/prompts/fix")
def fix_prompt(session: SessionDep, container: ContainerDep) -> dict:
    return container.prompts.fix(session)
