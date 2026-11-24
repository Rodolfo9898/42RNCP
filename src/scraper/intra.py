"""The intra website: its addresses, how it answers, and reading a project page (the only module that knows any of it)."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from .debug import PageDumper
from .exceptions import SessionExpired
from .http import HttpClient
from .models import FileLink, Link, ProjectInfo, Stats
from .reporting import Reporter
from .page import PageParser
from .utils import safe_name

SIGNIN_URL = "https://signin.intra.42.fr/users/sign_in"
PROJECTS_HOST = "projects.intra.42.fr"
PROJECTS_URL = f"https://{PROJECTS_HOST}"
LIST_URL = f"{PROJECTS_URL}/projects/list"
SITE_PREFIX = re.compile(r"^\s*Intra\s+Projects\b\s*", re.I)      # the page header of every project page


def project_url(slug: str) -> str:
    return f"{PROJECTS_URL}/projects/{slug}"


def on_intra(url: str) -> bool:
    """True for pages on the intra proper (i.e. not bounced to the sign-in / auth pages)."""
    host = urlparse(url).hostname or ""
    return host.endswith(".intra.42.fr") and host != "signin.intra.42.fr"


def clean_name(raw: str) -> str:
    return SITE_PREFIX.sub("", " ".join(raw.split()))


@dataclass(frozen=True)
class RawPage:
    url: str            # final URL, after redirects
    status: int
    body: bytes
    server: str = ""

    @property
    def html(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    @property
    def on_intra(self) -> bool:
        return on_intra(self.url)


class IntraGateway:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def _fetch(self, url: str, **kwargs) -> RawPage:
        response = self.http.get(url, **kwargs)
        return RawPage(str(response.url), response.status_code, response.content, response.headers.get("Server", ""))

    def project_page(self, slug: str) -> RawPage:
        return self._fetch(project_url(slug))

    def check_access(self) -> str | None:
        """None if we can read the intra's projects, else a short reason why not."""
        page = self._fetch(LIST_URL, params={"page": 1})
        head = page.body[:20_000].decode("utf-8", errors="replace")
        if page.status in (403, 503) and "cloudflare" in (page.server + head).lower():
            return f"blocked by a Cloudflare challenge (HTTP {page.status})"
        if not page.on_intra:
            return "not logged in (redirected to the sign-in page)"
        if page.status >= 400:
            return f"HTTP {page.status}"
        return None


class FileCollector:
    """Telling subject PDFs and artifacts apart among the links of a project page."""

    HOSTS = frozenset({"cdn.intra.42.fr", PROJECTS_HOST})
    PATH_PREFIXES = ("/pdf/", "/document/", "/uploads/")
    EXTENSIONS = frozenset({
        ".pdf", ".zip", ".tgz", ".gz", ".tar", ".bz2", ".xz", ".7z", ".rar",
        ".c", ".h", ".cpp", ".hpp", ".py", ".sh", ".txt", ".md", ".json", ".csv",
        ".mp3", ".mp4", ".mov", ".ova", ".iso", ".dmg", ".pkg", ".deb", ".bin",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    })
    IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"})

    def collect(self, links: Iterable[Link]) -> list[FileLink]:
        seen: set[str] = set()
        files: list[FileLink] = []
        for link in links:
            url = link.url.split("#", 1)[0]
            u = urlparse(url)
            if u.hostname not in self.HOSTS or url in seen:
                continue
            ext = Path(u.path).suffix.lower()
            if ext in self.IMAGE_EXTENSIONS or u.path.startswith("/users/"):
                continue
            if not (ext in self.EXTENSIONS or u.path.startswith(self.PATH_PREFIXES)):
                continue
            seen.add(url)
            files.append(FileLink(url=url, text=link.text, filename=safe_name(unquote(Path(u.path).name)) or "file"))
        return files


class ProjectReader:
    def __init__(self, gateway: IntraGateway, parser: PageParser, collector: FileCollector, reporter: Reporter,
                 dumper: PageDumper) -> None:
        self.gateway, self.parser, self.collector = gateway, parser, collector
        self.reporter, self.dumper = reporter, dumper

    def read(self, slug: str, stats: Stats) -> ProjectInfo | None:
        """Nothing is downloaded here. None when there is nothing to download."""
        log = self.reporter.log
        page = self.gateway.project_page(slug)
        if not page.on_intra:
            raise SessionExpired()
        if page.status >= 400:
            log(f"  ! HTTP {page.status}, skipping")
            stats.failed.append(f"{slug} (HTTP {page.status})")
            return None
        self.dumper.save(f"project-{slug}", page.html)
        parsed = self.parser.parse(page.html, page.url)
        name = clean_name(parsed.h1) or clean_name(parsed.title.split("|")[0]) or slug
        files = self.collector.collect(parsed.links)
        subjects = [f for f in files if f.is_subject]
        artifacts = [f for f in files if not f.is_subject]
        log(f"  {name!r}: {len(subjects)} subject PDF(s), {len(artifacts)} artifact(s)")
        if not files:
            log("  (no files on the page - you may not have access to this project's files)")
            stats.no_files.append(f"{name} ({slug})")
            return None
        if not subjects:
            log("  ! no subject PDF among the links, only artifacts")
        return ProjectInfo(slug, name, subjects, artifacts)
