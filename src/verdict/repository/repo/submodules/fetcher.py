"""Downloading the submodules of a project for the build.

A project's libs (libft, ft_printf, MiniLibX...) are often submodules that its Makefile downloads with `git submodule update`.
The sandbox has no network on purpose, so the app downloads them into the disposable copy before the build.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from verdict.repository.repo.git.client import GitClient
from verdict.repository.repo.model.records import SubmoduleNote
from verdict.repository.repo.submodules.download import SourcePolicy, SubmoduleDownload
from verdict.repository.repo.submodules.gitmodules import GitModules
from verdict.repository.repo.submodules.policy import HostPolicy

MAX_SUBMODULES = 10
SUBMODULE_DEPTH = 2                 # a lib may have libs of its own
SUBMODULE_BUDGET = 420              # for all of them


class SubmoduleFetcher:
    """Downloads the submodules of the project in a folder (a disposable copy) at the commits the project records, and the ones
    those have, down to SUBMODULE_DEPTH levels. Never raises: one note per submodule says what happened to it. A folder that
    already has content is left alone."""

    def __init__(self, client: GitClient, policy: SourcePolicy, *, protocols: tuple[str, ...] = ("https", "ssh"),
                 budget: float = SUBMODULE_BUDGET, clock: Callable[[], float] = time.monotonic) -> None:
        self.modules = GitModules(client)
        self.download = SubmoduleDownload(client, policy, protocols, clock)
        self.budget, self.clock = budget, clock

    def fetch(self, root: Path) -> list[SubmoduleNote]:
        return self._fetch(root, self.budget, 0, "")

    def _fetch(self, root: Path, budget: float, depth: int, prefix: str) -> list[SubmoduleNote]:
        deadline = self.clock() + budget
        try:
            links, urls = self.modules.gitlinks(root), self.modules.urls(root)
        except Exception as exc:
            return [SubmoduleNote("", False, f"could not read the submodules: {exc}")]
        notes: list[SubmoduleNote] = []
        for count, (path, sha) in enumerate(sorted(links.items())):
            shown = f"{prefix}{path}"
            if count >= MAX_SUBMODULES:
                notes.append(SubmoduleNote(shown, False, f"more than {MAX_SUBMODULES} submodules: this one was not downloaded"))
                continue
            try:
                notes.append(self.download.fetch(root, path, sha, urls.get(path, ""), shown, deadline))
            except Exception as exc:
                notes.append(SubmoduleNote(shown, False, f"{type(exc).__name__}: {exc}"))
            if notes[-1].ok and depth + 1 < SUBMODULE_DEPTH and (root / path / ".gitmodules").is_file():
                notes += self._fetch(root / path, max(0.0, deadline - self.clock()), depth + 1, f"{shown}/")
        return notes


def fetch_submodules(root: Path, known_hosts: Path, *, extra_hosts: set[str] | frozenset[str] = frozenset(),
                     protocols: tuple[str, ...] = ("https", "ssh"), budget: float = SUBMODULE_BUDGET,
                     clock: Callable[[], float] | None = None) -> list[SubmoduleNote]:
    """Download the submodules of the project in `root` (a disposable copy) at the commits the project records, so that the build
    does not need the network. Never raises. Returns one note per submodule; a folder that already has content is left alone.
    `extra_hosts`: the project's own host, besides the ones a submodule may always come from."""
    try:
        known_hosts.parent.mkdir(parents=True, exist_ok=True)
        client = GitClient.networked(known_hosts, global_config=False, protocols=protocols)
    except Exception as exc:
        return [SubmoduleNote("", False, f"could not read the submodules: {exc}")]
    fetcher = SubmoduleFetcher(client, HostPolicy(extra_hosts), protocols=protocols, budget=budget, clock=clock or time.monotonic)
    return fetcher.fetch(root)
