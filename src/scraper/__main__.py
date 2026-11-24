"""Entry point: python -m scraper [options]   (see --help)."""
from __future__ import annotations

import getpass
import sys

import httpx

from .cli import CommandFactory, build_parser
from .config import ROOT, Settings
from .exceptions import ScraperError
from .reporting import ConsoleReporter, Reporter
from .utils import first_line, load_env


def prompt_credentials() -> tuple[str, str]:
    """Ask for the intra login when it is not in .env (only on a terminal)."""
    if not sys.stdin.isatty():
        raise ScraperError("Not logged in: set INTRA_LOGIN and INTRA_PASSWORD in .env (or in the environment) and run it again.")
    login = input("42 intra login: ").strip()
    return login, getpass.getpass("42 intra password (not shown, not saved): ")


def main(argv: list[str] | None = None, *, settings: Settings | None = None, reporter: Reporter | None = None,
         factory: CommandFactory | None = None) -> None:
    """Parse the arguments, build the command, run it, turn failures into plain messages.
    `settings`, `reporter` and `factory` can be injected (the tests do); by default they come from .env."""
    args = build_parser().parse_args(argv)
    if settings is None:
        load_env(ROOT / ".env")
        settings = Settings.from_env(lang=args.lang, delay=args.delay, headed=args.headed, with_artifacts=not args.no_artifacts,
                                     with_children=not args.skip_children, with_experience=args.with_experience)
    factory = factory or CommandFactory(settings, reporter or ConsoleReporter(), ask=prompt_credentials)
    try:
        factory.create(args).execute()
    except ScraperError as exc:
        sys.exit(str(exc))
    except httpx.HTTPError as exc:
        sys.exit(f"\nNetwork error: {first_line(exc)}")
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")


if __name__ == "__main__":
    main()
