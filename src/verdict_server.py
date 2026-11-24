"""Main of the review app (the `web` container): `uvicorn verdict_server:app`."""

from verdict.app.factory import create_app

app = create_app()
