"""The web layer under test: the real app, built by `create_app` from a `Container` whose replaceable parts are the tests' own.

`client` is `(TestClient, harness)`; the harness is the container itself (`.store`, `.settings`, `.terminal`, `.sandbox`, `.folders`...).
Background work runs in the thread of the request (the `spawn` fixture can hold it); `threaded_client` is the real thing, for the few
tests where concurrency is the point."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import NORM_PAGES, SUBJECT_PAGES, make_pdf
from tests.verdict.api.support import FakeTerminal, Spawner
from verdict.app.container import Container
from verdict.app.factory import create_app
from verdict.app.settings import Settings
from verdict.core.background import in_thread


@pytest.fixture
def spawn() -> Spawner:
    return Spawner()


@pytest.fixture
def terminal() -> FakeTerminal:
    return FakeTerminal()


@pytest.fixture
def make_client(tmp_path, spawn, terminal):
    """Builds an app over empty temp folders and a library with push_swap.pdf and the Norm. Everything is replaceable per test."""
    def make(*, sandbox=None, terminal=terminal, spawn=spawn, progress_file=None):
        (tmp_path / "lib" / "common-core").mkdir(parents=True, exist_ok=True)
        (tmp_path / "lib" / "common-core" / "push_swap.pdf").write_bytes(make_pdf(SUBJECT_PAGES))
        (tmp_path / "lib" / "en.norm.pdf").write_bytes(make_pdf(NORM_PAGES))
        settings = Settings(workspace=tmp_path / "ws", projects=tmp_path / "projects", samples=tmp_path / "lib", progress_file=progress_file)
        container = Container(settings, sandbox=sandbox, terminal=terminal, spawn=spawn)
        return TestClient(create_app(container=container)), container
    return make


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def threaded_client(make_client):
    return make_client(spawn=in_thread)
