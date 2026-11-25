import pytest

from tests.scraper.support import World, make_world


@pytest.fixture
def world(tmp_path) -> World:
    """The service over a repository in a temporary folder, with a saved session; a download waits until the test runs it."""
    return make_world(tmp_path)


@pytest.fixture
def eager(tmp_path) -> World:
    """The same, but a download runs as soon as it is started (the request returns when it is over)."""
    return make_world(tmp_path, immediately=True)
