"""The command line, and the factory that turns it into the right Command."""
from __future__ import annotations

import argparse
from collections.abc import Callable

from .auth import Authenticator, BrowserAuthenticator, SessionManager
from .catalog import Catalog
from .commands import Command, PlanCommand, ScrapeCommand, select_targets
from .config import Settings
from .debug import HtmlDumper, NullDumper
from .http import HttpClient
from .library import Library
from .reporting import Reporter
from .tracks import TRACKS, build_plan

DESCRIPTION = """Fill samples/ (the subject PDFs) and artifacts/ (the files that come with a project) from the 42 intra.

    samples/common-core/libft.pdf          one folder per track, no sub-folders
    samples/post-common-core/scop.pdf
    samples/rncp/h42n42.pdf                every RNCP project of data/rncp_21.json, in this one folder
    artifacts/h42n42/...                   the other files of a project, in a folder named like its PDF

What is already there is never downloaded again. A real browser (Playwright) is used only to log in; everything else is plain
authenticated HTTP. INTRA_LOGIN and INTRA_PASSWORD come from .env (or are asked for).
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scraper", description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--track", "-t", action="append", choices=TRACKS, help="only this track (repeatable); default: all three")
    p.add_argument("--project", "-p", action="append", metavar="PROJECT",
                   help="only this project (repeatable): its slug, name, id or file name, e.g. libft or 42cursus-libft")
    p.add_argument("--dry-run", action="store_true", help="show what is missing and what would be visited; offline, nothing is fetched")
    p.add_argument("--unassigned", action="store_true", help="with --dry-run: also list the catalog's 42cursus projects that are in no track")
    p.add_argument("--force", action="store_true", help="download again what is already there")
    p.add_argument("--no-artifacts", action="store_true", help="only the subject PDFs (artifacts can be gigabytes)")
    p.add_argument("--skip-children", action="store_true", help="leave out the projects inside a piscine or a series (Django - 0, Day 00, ...)")
    p.add_argument("--with-experience", action="store_true", help="also the RNCP 'experience' projects (internships, work-study)")
    p.add_argument("--lang", default=None, help="preferred subject language (default: $SUBJECT_LANG or en)")
    p.add_argument("--delay", type=float, default=None, help="seconds between projects (default: $SCRAPE_DELAY or 1.5)")
    p.add_argument("--headed", action="store_true", help="show the browser window while logging in (2FA/captcha)")
    p.add_argument("--dump-html", action="store_true", help="save the fetched pages to .debug/ to tune the parsing")
    return p


class CommandFactory:
    """Also the composition root: the only place that decides which concrete classes are used. The authenticator, the HTTP
    client and the way credentials are asked for can be replaced (the tests do)."""

    def __init__(self, settings: Settings, reporter: Reporter, *, authenticator: Authenticator | None = None,
                 http_factory: Callable[[], HttpClient] | None = None, ask: Callable[[], tuple[str, str]] | None = None) -> None:
        self.settings, self.reporter = settings, reporter
        self.authenticator = authenticator or BrowserAuthenticator(settings, reporter)
        self.http_factory, self.ask = http_factory, ask

    def create(self, args: argparse.Namespace) -> Command:
        s = self.settings
        catalog = Catalog.load(s.data_dir / "projects_21.json")
        plan = build_plan(catalog, s.data_dir, with_children=s.with_children, with_experience=s.with_experience)
        library = Library(s.samples_dir, s.artifacts_dir)
        targets = select_targets(plan, catalog, tracks=args.track, projects=args.project)
        if args.dry_run:
            return PlanCommand(targets, plan, catalog, library, s, self.reporter, unassigned=args.unassigned)
        session = SessionManager(s, self.authenticator, self.reporter, self.http_factory, self.ask)
        dumper = HtmlDumper(s.debug_dir) if args.dump_html else NullDumper()
        return ScrapeCommand(targets=targets, settings=s, session=session, library=library, reporter=self.reporter,
                             dumper=dumper, force=args.force)
