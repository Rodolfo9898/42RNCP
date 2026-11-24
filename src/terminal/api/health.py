"""GET /health: is the service up, is claude installed, does it have the ssh-agent."""

import shutil

from fastapi import APIRouter

from terminal.settings.settings import Settings


def health_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok", "claude": shutil.which(settings.claude) is not None, "ssh": settings.ssh_agent_ready}

    return router
