"""The FastAPI app: its routes, its headers, and how a failure of the review is told."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from verdict.api import documents, health, library, projects, reviews, runs, sessions, subjects
from verdict.app.container import Container
from verdict.app.security import SecurityHeaders
from verdict.app.settings import Settings
from verdict.core.errors import VerdictError

ROUTERS = (health, library, sessions, subjects, projects, runs, reviews, documents)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    app = FastAPI(title="verdict")
    app.state.container = container or Container(settings or Settings.from_env())
    app.add_middleware(SecurityHeaders)
    app.add_exception_handler(VerdictError, tell)
    for module in ROUTERS:
        app.include_router(module.router)
    return app


async def tell(request: Request, exc: VerdictError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status)
