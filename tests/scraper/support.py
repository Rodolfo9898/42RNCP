"""Stand-ins for the scraper service tests: a tiny catalog, the in-memory intra of test_scraper.py, a client for the app."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from scraper.core.config import Settings
from scraper.jobs.runner import DownloadRunner
from scraper.server.app import create_app
from scraper.server.settings import ServiceSettings
from tests.scraper.test_scraper import PDF, FakeSite, entry, write_data

TOKEN = "scraper-token-for-tests"
HEADERS = {"x-scraper-token": TOKEN}

SLUGS = ["42cursus-libft", "cpp-module-00", "cpp-module-01", "42cursus-darkly", "42cursus-h42n42", "piscine-swift", "swift-0-intro"]


class Intra(FakeSite):
    """The in-memory intra, and a way to act when one of its project pages is asked for (to stop a download in the middle, say)."""

    def __init__(self) -> None:
        super().__init__()
        self.on_page: dict[str, Callable[[], None]] = {}

    def handler(self, request):
        slug = request.url.path.removeprefix("/projects/")
        if request.url.host == "projects.intra.42.fr" and slug in self.on_page:
            self.on_page[slug]()
        return super().handler(request)


class Starter:
    """Stands for the thread of a download: it keeps what it is asked to run, so the test decides when it happens."""

    def __init__(self, immediately: bool = False) -> None:
        self.immediately, self.waiting, self.started = immediately, [], 0

    def __call__(self, work: Callable[[], None]) -> None:
        self.started += 1
        work() if self.immediately else self.waiting.append(work)

    def run(self) -> None:
        while self.waiting:
            self.waiting.pop(0)()


@dataclass
class World:
    """A repository in a temporary folder with a four-line catalog, the intra it points to, and the service on top of both."""

    tmp: Path
    settings: Settings
    site: Intra
    starter: Starter
    runner: DownloadRunner
    client: TestClient

    def pdf(self, relative: str, content: bytes = PDF) -> Path:
        path = self.tmp / "samples" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def get(self, path: str, **params: str | list[str]):
        return self.client.get(path, headers=HEADERS, params=params)

    def post(self, path: str, body: dict | None = None):
        return self.client.post(path, headers=HEADERS, json=body)

    def delete(self, path: str):
        return self.client.delete(path, headers=HEADERS)

    def lines(self) -> list[str]:
        return self.get("/downloads/current").json()["lines"]


def data_folder(tmp: Path) -> Path:
    """libft and two cpp modules (common-core), darkly (post-common-core), h42n42 and a piscine with one child (rncp); an exam in no track."""
    return write_data(
        tmp / "data", common=["libft", "cpp-module-00", "cpp-module-01"], post=["darkly", "ft_lex"],
        rncp={"rncp": [{"options": [{"projects": [5, 6]}]}], "suite": {"projects": []}, "experience": {"projects": []}},
        projects=[entry(1, "Libft", "42cursus-libft"), entry(2, "Cpp Module 00", "cpp-module-00"), entry(3, "Cpp Module 01", "cpp-module-01"),
                  entry(4, "darkly", "42cursus-darkly"), entry(5, "h42n42", "42cursus-h42n42"),
                  entry(6, "Piscine Swift", "piscine-swift", [{"id": 7, "name": "Swift 0 Intro", "slug": "swift-0-intro"}]),
                  entry(7, "Swift 0 Intro", "swift-0-intro"), entry(8, "Exam Rank 02", "42cursus-exam-rank-02")])


def make_world(tmp: Path, *, session: bool = True, immediately: bool = False, token: str = TOKEN, own_http: bool = False) -> World:
    """`own_http`: the service reaches the intra the way it does for real (a client made from the saved files), not through `site`."""
    settings = Settings(samples_dir=tmp / "samples", artifacts_dir=tmp / "artifacts", data_dir=data_folder(tmp), session_dir=tmp / "session",
                        delay=0)
    if session:
        settings.session_dir.mkdir(parents=True)
        settings.state_file.write_text("{}")
    site, starter = Intra(), Starter(immediately)
    for slug in SLUGS:
        site.add_project(slug, slug, artifacts=("tests.tgz",))
    runner = DownloadRunner(starter, new_id=iter(f"job-{n}" for n in range(1, 100)).__next__)
    app = create_app(ServiceSettings(token, settings), http_factory=None if own_http else site.http, runner=runner)
    return World(tmp, settings, site, starter, runner, TestClient(app))
