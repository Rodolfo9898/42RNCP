"""Main of the review app (the `web` container): `uvicorn verdict_server:app`."""

from verdict.app.server import app

__all__ = ["app"]
