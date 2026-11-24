"""The subject scraper (scraper/): the plan from the lists, naming, what is on disk, and a whole run against an in-memory intra."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from scraper.cli.main import main
from scraper.site.login import Authenticator, SessionManager
from scraper.plan.catalog import Catalog
from scraper.cli.parser import CommandFactory, build_parser
from scraper.cli.commands import PlanCommand, ScrapeCommand, select_targets
from scraper.core.config import DATA, ROOT, Settings
from scraper.core.debug import NullDumper
from scraper.storage.download import FileDownloader
from scraper.core.exceptions import ScraperError
from scraper.site.http import HttpClient
from scraper.site.gateway import FileCollector, IntraGateway, ProjectReader, SIGNIN_URL
from scraper.storage.library import Library
from scraper.core.models import Link, Stats
from scraper.plan.names import key, stem
from scraper.site.page import PageParser
from scraper.core.reporting import Reporter
from scraper.plan.tracks import TRACKS, Target, build_plan, rncp_ids
from scraper.core.utils import load_env, prune_empty

PDF = b"%PDF-1.4\n" + b"x" * 2000


class Buffer(Reporter):
    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, message: str = "") -> None:
        self.lines.append(message)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def settings(tmp: Path, **overrides) -> Settings:
    base = dict(login="tester", password="pw", samples_dir=tmp / "samples", artifacts_dir=tmp / "artifacts", state_file=tmp / ".session" / "state.json",
                user_agent_file=tmp / ".session" / "ua.txt", debug_dir=tmp / ".debug", delay=0)
    return Settings(**{**base, **overrides})


# ---------------------------------------------------------------------------------------------- an in-memory intra


def page(body: str, title: str = "Intra") -> bytes:
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>".encode()


class FakeSite:
    """Stands in for projects.intra.42.fr, cdn.intra.42.fr and the sign-in page."""

    def __init__(self) -> None:
        self.projects: dict[str, bytes] = {}
        self.files: dict[str, tuple[int, str, bytes]] = {}
        self.requests: list[str] = []
        self.logged_in = True
        self.cloudflare = False
        self._ids = iter(range(1, 10_000))

    def add_project(self, slug: str, name: str, *, subjects: tuple[str, ...] = ("en",), artifacts: tuple[str, ...] = (),
                    broken_subject: bool = False) -> None:
        links = []
        for lang in subjects:
            path = f"/pdf/pdf/{next(self._ids)}/{lang}.subject.pdf"
            links.append(f'<a href="https://cdn.intra.42.fr{path}">{lang} subject</a>')
            self.files[path] = (200, "application/pdf", b"<html>login</html>" if broken_subject else PDF)
        for filename in artifacts:
            path = f"/document/document/{next(self._ids)}/{filename}"
            links.append(f'<a href="https://cdn.intra.42.fr{path}">{filename}</a>')
            self.files[path] = (200, "application/octet-stream", b"artifact:" + filename.encode())
        self.projects[slug] = page(f"<h1>Intra Projects {name}</h1>{''.join(links)}", f"{name} | Intra")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        host, path = request.url.host, request.url.path
        if host == "signin.intra.42.fr":
            return httpx.Response(200, content=page("sign in"))
        if host == "cdn.intra.42.fr":
            status, ctype, body = self.files.get(path, (404, "text/plain", b"nope"))
            return httpx.Response(status, content=body, headers={"Content-Type": ctype})
        if self.cloudflare:
            return httpx.Response(403, content=page("Just a moment... cloudflare"), headers={"Server": "cloudflare"})
        if not self.logged_in:
            return httpx.Response(302, headers={"Location": SIGNIN_URL})
        if path == "/projects/list":
            return httpx.Response(200, content=page("projects"))
        slug = path.removeprefix("/projects/")
        if slug in self.projects:
            return httpx.Response(200, content=self.projects[slug], headers={"Content-Type": "text/html"})
        return httpx.Response(404, content=page("not found"))

    def http(self) -> HttpClient:
        return HttpClient(transport=httpx.MockTransport(self.handler), sleep=lambda _: None)


class FakeAuthenticator(Authenticator):
    def __init__(self, site: FakeSite) -> None:
        self.site, self.calls = site, []

    def login(self, login: str, password: str) -> None:
        self.calls.append((login, password))
        self.site.logged_in = True


def write_data(folder: Path, *, common=(), post=(), rncp=None, projects=()) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "common-core.txt").write_text("\n".join(common))
    (folder / "post-common-core.txt").write_text("\n".join(post))
    (folder / "rncp_21.json").write_text(json.dumps(rncp or {"rncp": [], "suite": {"projects": []}, "experience": {"projects": []}}))
    (folder / "projects_21.json").write_text(json.dumps({"projects": list(projects)}))
    return folder


def entry(pid: int, name: str, slug: str, children=()) -> dict:
    return {"id": pid, "name": name, "slug": slug, "children": list(children)}


def run_scrape(tmp: Path, site: FakeSite, targets: list[Target], **kw) -> tuple[Buffer, FakeAuthenticator, Library]:
    s = kw.pop("settings", None) or settings(tmp)
    reporter, auth = Buffer(), FakeAuthenticator(site)
    library = Library(s.samples_dir, s.artifacts_dir)
    session = SessionManager(s, auth, reporter, site.http)
    ScrapeCommand(targets=targets, settings=s, session=session, library=library, reporter=reporter, dumper=NullDumper(), **kw).execute()
    return reporter, auth, library


def target(track: str, slug: str, pid: int = 1, name: str = "") -> Target:
    from scraper.plan.catalog import Project
    return Target(track, Project(pid, name or slug, slug))


# ------------------------------------------------------------------------------------------------------- names


@pytest.mark.parametrize("slug,expected", [
    ("42cursus-libft", "libft"), ("cpp-module-03", "cpp03"), ("42cursus-kfs-1", "kfs1"), ("42cursus-kfs-x", "kfsx"),
    ("42cursus-fract-ol", "fractol"), ("42cursus-expert-system", "expert-systems"), ("music-room", "music_room"),
    ("42cursus-snow-crash", "snow_crash"), ("ready-set-boole", "ready_set_boole"), ("42cursus-ft_ssl_md5", "ft_ssl_md5"),
    ("django-0-initiation", "django-0-initiation"), ("Inception-of-Things", "inception-of-things"), ("b", "b"),
])
def test_the_name_on_disk_keeps_what_the_subjects_were_already_called(slug, expected):
    assert stem(slug) == expected


def test_the_review_still_reads_the_names_it_depends_on():
    from shared.constants import strict_layout
    from verdict.subjects.spec import _cpp_module
    assert _cpp_module(f"{stem('cpp-module-07')}.pdf", "") == 7
    assert strict_layout([f"{stem('42cursus-libft')}.pdf", f"{stem('42cursus-get_next_line')}.pdf", f"{stem('42cursus-ft_printf')}.pdf"])
    assert not strict_layout([f"{stem('42cursus-push_swap')}.pdf"])


def test_two_spellings_of_a_project_are_the_same_one():
    assert key("kfs-1") == key("kfs1") == key("Kfs_1") == "kfs1"


# ----------------------------------------------------------------------------------------------- catalog, tracks


def test_the_catalog_finds_a_project_by_slug_id_or_name_and_completes_children_given_by_id(tmp_path):
    data = write_data(tmp_path / "d", projects=[
        entry(1, "Libft", "42cursus-libft"), entry(2, "Piscine Swift iOS", "piscine-swift", [{"id": 3}, {"id": 4, "name": "Day 1", "slug": "swift-1"}]),
        entry(3, "Swift 0", "swift-0"), entry(5, "Cpp Module 00", "cpp-module-00"), entry(6, "Cpp  Module 01", "other")])
    catalog = Catalog.load(data / "projects_21.json")
    assert catalog.resolve("libft").id == catalog.resolve("42cursus-libft").id == catalog.resolve("1").id == catalog.resolve("LIBFT").id == 1
    assert catalog.resolve("cppmodule00").id == 5 and catalog.resolve("nope") is None
    assert [c.slug for c in catalog.by_id[2].children] == ["swift-0", "swift-1"]       # id-only child completed from its own entry
    assert catalog.resolve("Piscine Swift  iOS").id == 2


def test_the_plan_follows_the_three_lists_and_the_priority_between_them(tmp_path):
    data = write_data(tmp_path / "d", common=["libft", "# a comment", "", "so_long  # trailing"], post=["scop", "darkly", "ft_lex", "libft"],
                      rncp={"rncp": [{"options": [{"projects": [2, 99, 2]}, {"projects": [3]}]}], "suite": {"projects": [4]},
                            "experience": {"projects": [5]}},
                      projects=[entry(1, "Libft", "42cursus-libft"), entry(2, "darkly", "42cursus-darkly"), entry(3, "Piscine X", "piscine-x", [
                          {"id": 30, "name": "X - 0", "slug": "x-0"}]), entry(4, "42sh", "42cursus-42sh"), entry(5, "Internship I", "internship-i"),
                          entry(6, "scop", "42cursus-scop"), entry(7, "so_long", "so_long")])
    catalog = Catalog.load(data / "projects_21.json")
    plan = build_plan(catalog, data)
    assert [t.stem for t in plan.of("common-core")] == ["libft", "so_long"]
    assert [t.stem for t in plan.of("rncp")] == ["42sh", "darkly", "piscine-x", "x-0"]         # children follow their parent, once each, no experience
    assert [t.stem for t in plan.of("post-common-core")] == ["scop"] and plan.unresolved == {"rncp": ["id 99"], "post-common-core": ["ft_lex"]}
    assert plan.of("rncp")[3].parent.slug == "piscine-x"
    assert "internship-i" in [t.stem for t in build_plan(catalog, data, with_experience=True).of("rncp")]
    assert [t.stem for t in build_plan(catalog, data, with_children=False).of("rncp")] == ["42sh", "darkly", "piscine-x"]


def test_the_rncp_file_lists_every_project_once():
    ids = rncp_ids(DATA / "rncp_21.json")
    assert len(ids) == len(set(ids)) == 102 and 1481 in ids and 1429 in ids       # 98 in the options, h42n42 among them, and 4 more in "suite"
    assert 1854 in ids
    assert 1638 not in ids and 1638 in rncp_ids(DATA / "rncp_21.json", with_experience=True)


def test_the_shipped_lists_resolve_and_match_what_samples_already_holds():
    catalog = Catalog.load(DATA / "projects_21.json")
    plan = build_plan(catalog, DATA)
    assert set(plan.unresolved) <= {"post-common-core"}                        # only ft_lex and ft_yacc are not in the catalog snapshot yet
    assert not [name for names in plan.unresolved.values() for name in names if name not in ("ft_lex", "ft_yacc")]
    stems = [t.stem for t in plan.targets]
    assert len(stems) == len(set(stems)) and {t.track for t in plan.targets} == set(TRACKS)
    assert {"libft", "cpp09", "so_long"} <= {t.stem for t in plan.of("common-core")} and "h42n42" in {t.stem for t in plan.of("rncp")}
    by_key = {key(t.stem): t.track for t in plan.targets}
    not_in_the_catalog = {key(name) for names in plan.unresolved.values() for name in names}      # (ft_lex: a PDF you have, a project it does not list)
    for track in TRACKS:                                                       # what you already have is recognised, in the same track
        for pdf in sorted((ROOT / "samples" / track).rglob("*.pdf")):
            if key(pdf.stem) not in not_in_the_catalog:
                assert by_key.get(key(pdf.stem)) == track, f"{track}/{pdf.name} is not in the plan"


# ---------------------------------------------------------------------------------------------- the library on disk


def test_the_library_sees_a_pdf_in_any_track_under_any_spelling(tmp_path):
    for rel in ("samples/rncp/kfs1.pdf", "samples/common-core/cpp-modules/cpp00.pdf", "samples/rncp/notes.txt"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(PDF)
    library = Library(tmp_path / "samples", tmp_path / "artifacts")
    assert library.find_pdf("kfs-1").name == "kfs1.pdf" and library.find_pdf("cpp00").parent.name == "cpp-modules"     # (in a series folder too)
    assert library.find_pdf("kfs2") is None and library.pdf_path(target("rncp", "42cursus-h42n42")) == tmp_path / "samples" / "rncp" / "h42n42.pdf"


def test_checked_projects_are_remembered_and_a_broken_marker_is_ignored(tmp_path):
    library = Library(tmp_path / "samples", tmp_path / "artifacts")
    assert library.checked() == set()
    library.mark_checked("b"), library.mark_checked("a")
    assert library.checked() == {"a", "b"}
    (tmp_path / "artifacts" / ".checked.json").write_text("{not json")
    assert library.checked() == set()


def test_prune_empty_removes_the_empty_folders_only(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "file").write_text("x")
    prune_empty(tmp_path / "a" / "b", tmp_path)
    prune_empty(tmp_path / "keep", tmp_path)
    assert not (tmp_path / "a").exists() and (tmp_path / "keep" / "file").exists()


# ------------------------------------------------------------------------------------------------------ http


def test_the_client_retries_a_busy_server_and_waits_as_told():
    calls, waits = [], []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}) if len(calls) == 1 else (
            httpx.Response(503) if len(calls) == 2 else httpx.Response(200, content=b"ok"))

    client = HttpClient(transport=httpx.MockTransport(handler), sleep=waits.append)
    assert client.get("https://projects.intra.42.fr/x").content == b"ok" and waits == [7.0, 2.0 ** 1]


def test_the_client_gives_up_after_its_retries_and_retries_network_errors():
    def always_down(request):
        raise httpx.ConnectError("down")

    waits: list[float] = []
    with pytest.raises(httpx.ConnectError):
        HttpClient(transport=httpx.MockTransport(always_down), sleep=waits.append).get("https://x.test/")
    assert len(waits) == HttpClient.RETRIES
    persistent = HttpClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)), sleep=lambda _: None)
    assert persistent.get("https://x.test/").status_code == 500


def test_the_client_uses_the_cookies_and_agent_of_the_browser_login(tmp_path):
    state, agent = tmp_path / "state.json", tmp_path / "ua.txt"
    state.write_text(json.dumps({"cookies": [
        {"name": "live", "value": "1", "domain": ".intra.42.fr", "path": "/", "expires": time.time() + 3600},
        {"name": "old", "value": "2", "domain": ".intra.42.fr", "path": "/", "expires": time.time() - 5},
        {"name": "session", "value": "3", "domain": ".intra.42.fr", "path": "/", "expires": -1}]}))
    agent.write_text("MyBrowser/1.0\n")
    seen = {}
    client = HttpClient.from_saved_session(state, agent, transport=httpx.MockTransport(
        lambda r: (seen.update(cookie=r.headers.get("cookie", ""), agent=r.headers["user-agent"]), httpx.Response(200))[1]))
    client.get("https://projects.intra.42.fr/")
    assert "live=1" in seen["cookie"] and "session=3" in seen["cookie"] and "old=2" not in seen["cookie"] and seen["agent"] == "MyBrowser/1.0"


# ---------------------------------------------------------------------------------------- reading the intra


def test_a_project_page_gives_its_subject_and_its_artifacts():
    site = FakeSite()
    site.add_project("42cursus-demo", "Demo", subjects=("fr", "en"), artifacts=("tests.tgz", "vm.ova"))
    reporter, stats = Buffer(), Stats()
    info = ProjectReader(IntraGateway(site.http()), PageParser(), FileCollector(), reporter, NullDumper()).read("42cursus-demo", stats)
    assert info.name == "Demo" and [s.lang for s in info.subjects] == ["fr", "en"] and [a.filename for a in info.artifacts] == ["tests.tgz", "vm.ova"]


def test_a_page_without_files_a_missing_page_and_a_lost_session_are_reported():
    site = FakeSite()
    site.projects["empty"] = page("<h1>Intra Projects Empty</h1><a href='/projects/other'>other</a><a href='https://cdn.intra.42.fr/x.png'>img</a>")
    reader = ProjectReader(IntraGateway(site.http()), PageParser(), FileCollector(), Buffer(), NullDumper())
    stats = Stats()
    assert reader.read("empty", stats) is None and stats.no_files == ["Empty (empty)"]
    assert reader.read("missing", stats) is None and stats.failed == ["missing (HTTP 404)"]
    site.logged_in = False
    with pytest.raises(ScraperError, match="session expired"):
        reader.read("empty", stats)


def test_access_is_checked_before_anything_is_downloaded():
    site = FakeSite()
    assert IntraGateway(site.http()).check_access() is None
    site.logged_in = False
    assert "not logged in" in IntraGateway(site.http()).check_access()
    site.cloudflare = True
    assert "Cloudflare" in IntraGateway(site.http()).check_access()


def test_files_are_told_apart_by_host_extension_and_path():
    links = [Link("https://cdn.intra.42.fr/pdf/pdf/1/en.subject.pdf", "subject"), Link("https://cdn.intra.42.fr/document/document/2/t.tgz", "tests"),
             Link("https://cdn.intra.42.fr/users/me.jpg", "me"), Link("https://evil.example/x.zip", "no"), Link("https://cdn.intra.42.fr/a.png", "img"),
             Link("https://cdn.intra.42.fr/pdf/pdf/1/en.subject.pdf#page=2", "again")]
    files = FileCollector().collect(links)
    assert [f.filename for f in files] == ["en.subject.pdf", "t.tgz"] and [f.is_subject for f in files] == [True, False]


# ------------------------------------------------------------------------------------------------ a whole run


def test_a_run_puts_the_pdf_in_its_track_and_the_artifacts_beside_samples(tmp_path):
    site = FakeSite()
    site.add_project("42cursus-h42n42", "h42n42", artifacts=("tests.tgz", "vm.ova"))
    site.add_project("cpp-module-03", "CPP Module 03")
    first, second = target("rncp", "42cursus-h42n42", 1), target("common-core", "cpp-module-03", 2)
    reporter, _, library = run_scrape(tmp_path, site, [first, second])
    assert (tmp_path / "samples" / "rncp" / "h42n42.pdf").read_bytes() == PDF
    assert (tmp_path / "samples" / "common-core" / "cpp03.pdf").is_file()                 # named like the review expects, not like the page
    assert sorted(f.name for f in library.artifact_files(first)) == ["tests.tgz", "vm.ova"]
    assert (tmp_path / "artifacts" / "h42n42" / "tests.tgz").read_bytes() == b"artifact:tests.tgz"
    assert not (tmp_path / "samples" / "rncp" / "artifacts").exists() and not list((tmp_path / "samples").rglob("*.part"))
    assert library.checked() == {"h42n42", "cpp03"} and "Done: 2 subject(s) and 2 artifact(s)" in reporter.text


def test_what_is_already_there_is_not_downloaded_again_even_under_another_spelling(tmp_path):
    site = FakeSite()
    site.add_project("42cursus-kfs-1", "kfs-1", artifacts=("a.tgz",))
    (tmp_path / "samples" / "rncp").mkdir(parents=True)
    (tmp_path / "samples" / "rncp" / "kfs1.pdf").write_bytes(b"mine")
    run_scrape(tmp_path, site, [target("rncp", "42cursus-kfs-1")])
    assert [p.name for p in (tmp_path / "samples" / "rncp").iterdir()] == ["kfs1.pdf"] and (tmp_path / "samples/rncp/kfs1.pdf").read_bytes() == b"mine"
    assert (tmp_path / "artifacts" / "kfs1" / "a.tgz").is_file()                          # its artifacts are still fetched


def test_the_second_run_visits_nothing_and_force_downloads_again(tmp_path):
    site = FakeSite()
    site.add_project("scop", "scop", artifacts=("x.zip",))
    t = [target("post-common-core", "scop")]
    run_scrape(tmp_path, site, t)
    visited = len(site.requests)
    reporter, auth, _ = run_scrape(tmp_path, site, t)
    assert len(site.requests) == visited and "Nothing to do" in reporter.text
    (tmp_path / "samples/post-common-core/scop.pdf").write_bytes(b"old")
    run_scrape(tmp_path, site, t, force=True)
    assert (tmp_path / "samples/post-common-core/scop.pdf").read_bytes() == PDF


def test_without_artifacts_only_the_subject_comes_and_a_present_pdf_needs_no_visit(tmp_path):
    site = FakeSite()
    site.add_project("scop", "scop", artifacts=("big.iso",))
    s = settings(tmp_path, with_artifacts=False)
    run_scrape(tmp_path, site, [target("post-common-core", "scop")], settings=s)
    assert (tmp_path / "samples/post-common-core/scop.pdf").is_file() and not (tmp_path / "artifacts" / "scop").exists()
    before = len(site.requests)
    reporter, _, _ = run_scrape(tmp_path, site, [target("post-common-core", "scop")], settings=s)
    assert len(site.requests) == before and "Nothing to do" in reporter.text


def test_a_broken_download_is_reported_leaves_no_file_and_is_retried_next_time(tmp_path):
    site = FakeSite()
    site.add_project("bad", "bad", broken_subject=True)
    site.add_project("good", "good")
    reporter, _, library = run_scrape(tmp_path, site, [target("rncp", "bad", 1), target("rncp", "good", 2)])
    assert not (tmp_path / "samples/rncp/bad.pdf").exists() and (tmp_path / "samples/rncp/good.pdf").is_file()
    assert "did not return a PDF" in reporter.text and "1 failure(s)" in reporter.text
    assert library.checked() == {"good"} and not list(tmp_path.rglob("*.part"))


def test_a_project_that_the_intra_does_not_show_does_not_stop_the_others(tmp_path):
    site = FakeSite()
    site.add_project("good", "good")
    reporter, _, _ = run_scrape(tmp_path, site, [target("rncp", "gone", 1), target("rncp", "good", 2)])
    assert (tmp_path / "samples/rncp/good.pdf").is_file() and "HTTP 404" in reporter.text


def test_two_files_with_one_name_are_both_kept(tmp_path):
    site = FakeSite()
    site.add_project("p", "p", artifacts=("a.zip",))
    site.projects["p"] = site.projects["p"].replace(b"</body>", b'<a href="https://cdn.intra.42.fr/document/other/a.zip">dup</a></body>')
    site.files["/document/other/a.zip"] = (200, "application/zip", b"second")
    only = target("rncp", "p")
    _, _, library = run_scrape(tmp_path, site, [only])
    assert sorted(f.name for f in library.artifact_files(only)) == ["a.zip", "a_2.zip"]


def test_the_download_writes_through_a_part_file_and_rejects_non_pdfs(tmp_path):
    site = FakeSite()
    site.files["/pdf/x.pdf"] = (200, "application/pdf", b"not really a pdf")
    site.files["/pdf/ok.pdf"] = (200, "application/pdf", PDF)
    downloader = FileDownloader(site.http(), Buffer())
    assert downloader.download("https://cdn.intra.42.fr/pdf/x.pdf", tmp_path / "x.pdf", pdf=True) is None and not (tmp_path / "x.pdf").exists()
    assert downloader.download("https://cdn.intra.42.fr/pdf/ok.pdf", tmp_path / "d" / "ok.pdf", pdf=True) == len(PDF)
    assert downloader.download("https://cdn.intra.42.fr/missing", tmp_path / "m", pdf=False) is None and not list(tmp_path.rglob("*.part"))


# ------------------------------------------------------------------------------------- login and the session


def test_a_valid_saved_session_is_reused_and_a_stale_one_logs_in_again(tmp_path):
    site, reporter = FakeSite(), Buffer()
    s = settings(tmp_path, login="me", password="pw")
    auth = FakeAuthenticator(site)
    SessionManager(s, auth, reporter, site.http).open()                       # no state file yet: logs in
    assert auth.calls == [("me", "pw")]
    s.state_file.parent.mkdir(parents=True), s.state_file.write_text("{}")
    SessionManager(s, auth, reporter, site.http).open()
    assert len(auth.calls) == 1 and "Reusing saved session" in reporter.text
    site.logged_in = False
    SessionManager(s, auth, reporter, site.http).open()
    assert len(auth.calls) == 2 and "Saved session not usable" in reporter.text


def test_without_credentials_the_login_is_asked_for_or_explained(tmp_path):
    site = FakeSite()
    site.logged_in = False
    auth = FakeAuthenticator(site)
    nobody = settings(tmp_path, login=None, password=None)
    SessionManager(nobody, auth, Buffer(), site.http, ask=lambda: ("typed", "secret")).open()
    assert auth.calls == [("typed", "secret")]
    with pytest.raises(ScraperError, match="INTRA_LOGIN and INTRA_PASSWORD"):
        SessionManager(nobody, FakeAuthenticator(site), Buffer(), site.http).open()


def test_a_login_that_http_still_cannot_use_is_an_error(tmp_path):
    site = FakeSite()
    site.logged_in = False

    class Useless(Authenticator):
        def login(self, login, password):
            pass

    with pytest.raises(ScraperError, match="not logged in"):
        SessionManager(settings(tmp_path, login="a", password="b"), Useless(), Buffer(), site.http).open()


def test_load_env_sets_only_what_is_missing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# c\nINTRA_LOGIN=me\nINTRA_PASSWORD='p w'\nexport EXTRA=1\nTERMINAL_TOKEN=from-file\n=bad\nnoequals\n")
    monkeypatch.delenv("INTRA_LOGIN", raising=False), monkeypatch.delenv("INTRA_PASSWORD", raising=False), monkeypatch.delenv("EXTRA", raising=False)
    monkeypatch.setenv("TERMINAL_TOKEN", "already")
    load_env(env)
    import os
    assert (os.environ["INTRA_LOGIN"], os.environ["INTRA_PASSWORD"], os.environ["EXTRA"], os.environ["TERMINAL_TOKEN"]) == ("me", "p w", "1", "already")
    load_env(tmp_path / "missing")                                           # no file: nothing happens


# ------------------------------------------------------------------------------- the command line and --dry-run


def factory_for(tmp: Path, site: FakeSite | None = None, **kw) -> tuple[CommandFactory, Buffer]:
    reporter = Buffer()
    s = settings(tmp, **kw)
    if site is None:
        def no_network():
            raise AssertionError("a dry run must not touch the network")
        return CommandFactory(s, reporter, authenticator=None, http_factory=no_network), reporter
    return CommandFactory(s, reporter, authenticator=FakeAuthenticator(site), http_factory=site.http), reporter


def test_dry_run_lists_what_is_missing_offline(tmp_path):
    (tmp_path / "samples" / "common-core").mkdir(parents=True)
    (tmp_path / "samples" / "common-core" / "libft.pdf").write_bytes(PDF)
    factory, reporter = factory_for(tmp_path)
    factory.create(build_parser().parse_args(["--dry-run", "--track", "common-core"])).execute()
    assert "common-core: 28 project(s), 1 with a PDF, 27 missing" in reporter.text and "samples/common-core/so_long.pdf" in reporter.text
    assert "libft.pdf" not in reporter.text and "rncp:" not in reporter.text and "Nothing was downloaded" in reporter.text
    assert not (tmp_path / "artifacts").exists()


def test_dry_run_reports_names_the_catalog_does_not_know_and_can_list_the_unassigned(tmp_path):
    factory, reporter = factory_for(tmp_path)
    factory.create(build_parser().parse_args(["--dry-run", "--unassigned"])).execute()
    assert "? ft_lex: not in the catalog" in reporter.text and "in no track" in reporter.text


def test_projects_and_tracks_narrow_the_plan_and_unknown_ones_are_explained(tmp_path):
    catalog = Catalog.load(DATA / "projects_21.json")
    plan = build_plan(catalog, DATA)
    assert [t.stem for t in select_targets(plan, catalog, tracks=None, projects=["libft", "42cursus-darkly", "kfs-1"])] == ["libft", "darkly", "kfs1"]
    assert {t.track for t in select_targets(plan, catalog, tracks=["rncp"], projects=None)} == {"rncp"}
    assert select_targets(plan, catalog, tracks=["rncp"], projects=["libft"]) == []        # libft is not in that track
    with pytest.raises(ScraperError, match="catalog does not know"):
        select_targets(plan, catalog, tracks=None, projects=["no-such-project"])
    with pytest.raises(ScraperError, match="in no track"):
        select_targets(plan, catalog, tracks=None, projects=["exam-rank-02"])


def test_main_runs_a_selected_project_and_turns_errors_into_messages(tmp_path):
    site = FakeSite()
    site.add_project("42cursus-libft", "Libft")
    factory, reporter = factory_for(tmp_path, site)
    main(["-p", "libft"], settings=settings(tmp_path), reporter=reporter, factory=factory)
    assert (tmp_path / "samples" / "common-core" / "libft.pdf").is_file()
    with pytest.raises(SystemExit, match="catalog does not know"):
        main(["-p", "nope"], settings=settings(tmp_path), reporter=reporter, factory=factory)


def test_the_library_the_scraper_writes_is_the_one_the_app_reads(tmp_path):
    """A downloaded PDF lands where verdict's library looks: samples/<track>/<name>.pdf."""
    from verdict.library.catalog import TRACKS as APP_TRACKS, LibraryService
    assert set(TRACKS) == set(APP_TRACKS)
    site = FakeSite()
    site.add_project("cpp-module-02", "CPP Module 02")
    run_scrape(tmp_path, site, [target("common-core", "cpp-module-02")])
    assert "common-core/cpp02.pdf" in LibraryService(tmp_path / "samples").files()


# --------------------------------------------------------------------- what must never end up in git or an image


def test_artifacts_and_the_login_session_stay_out_of_git_and_the_docker_build():
    gitignore = (ROOT / ".gitignore").read_text().split()
    for entry_ in (".session/", ".scraper-venv/"):
        assert entry_ in gitignore, f"{entry_} must be in .gitignore"
    for ignore in sorted((ROOT / "docker").glob("*/Dockerfile.dockerignore")):          # every image: only what its Dockerfile copies in
        lines = ignore.read_text().split()
        assert "*" in lines and not {"!artifacts", "!.session", "!samples", "!projects", "!.env"} & set(lines), ignore
    assert "artifacts" not in (ROOT / "docker-compose.yml").read_text()               # the containers never see them
