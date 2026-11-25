"""GET /health: is the service up."""
from __future__ import annotations

from fastapi import APIRouter


def health_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return router
