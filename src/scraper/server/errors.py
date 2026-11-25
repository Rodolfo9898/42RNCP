"""How the service's errors look to the caller: always `{"detail": "..."}`, with the status that says whose fault it is."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from scraper.core.exceptions import ScraperError
from scraper.jobs.runner import AlreadyRunning


def install_error_handlers(app: FastAPI) -> None:
    async def refused(request: Request, exc: ScraperError) -> JSONResponse:
        return JSONResponse({"detail": str(exc).strip()}, status_code=400)         # an expected failure: the message is for the person

    async def busy(request: Request, exc: AlreadyRunning) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    async def malformed(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(f"{'.'.join(str(part) for part in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"detail": problems or "invalid request"}, status_code=422)

    app.add_exception_handler(ScraperError, refused)
    app.add_exception_handler(AlreadyRunning, busy)
    app.add_exception_handler(RequestValidationError, malformed)
