"""The scratch copy of a repository that the headless review reads."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from shared.constants import GENERATED_VERDICT_NAMES, SKIPPED_NAMES, VERDICT_MARKER
from terminal.environment.child import ChildEnvironment
from terminal.settings.limits import Limits
from terminal.settings.settings import Settings

# Replaces .git/config in the copy: enough for git to read the history, nothing that runs a program.
SAFE_GIT_CONFIG = "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = false\n\tlogallrefupdates = true\n"
# The only remote addresses carried into the copy: plain ssh or https, never `ext::`, a local path or anything that starts with "-".
SAFE_REMOTE_URL = re.compile(r"(git@[A-Za-z0-9.-]+:|ssh://git@[A-Za-z0-9.-]+(:[0-9]+)?/|https://[A-Za-z0-9.-]+/)[A-Za-z0-9._~/+-]+")
TOP = Path(".")
GIT = Path(".git")


class CopyBudget:
    """How much one copy may take: the files and bytes counted so far against the limits."""

    def __init__(self, limits: Limits) -> None:
        self.limits, self.files, self.bytes = limits, 0, 0

    def charge(self, size: int) -> None:
        self.files, self.bytes = self.files + 1, self.bytes + size
        if self.files > self.limits.max_copy_files or self.bytes > self.limits.max_copy_bytes:
            raise ValueError("repository is too large to copy for the review")


class SanitizedCopy:
    """Copies a repository, which is untrusted data, into a fresh scratch directory for claude to read.

    The files that configure or instruct claude (.claude/, CLAUDE.md, .mcp.json) and all symlinks are left out. The clone's .git is
    kept so that git works, but never its hooks or its config (a fresh minimal one replaces it, so nothing in .git can make git run
    a program), and a verdict of ours from an earlier run is left out so that claude judges the project afresh.
    (Builder: fixed steps, walk, filter, copy within a budget, safe git config, each a method of its own.)"""

    def __init__(self, settings: Settings, environment: ChildEnvironment) -> None:
        self.settings, self.environment = settings, environment

    def make(self, source: Path) -> Path:
        self.settings.scratch.mkdir(parents=True, exist_ok=True)
        destination = Path(tempfile.mkdtemp(prefix="repo-", dir=self.settings.scratch))
        try:
            self._copy_tree(source, destination)
            if (destination / GIT).is_dir():
                (destination / GIT / "config").write_text(self._git_config(source))
        except Exception:
            self.cleanup(destination)                 # (a copy that was refused leaves nothing behind)
            raise
        return destination

    def cleanup(self, path: Path) -> None:
        if path.resolve().is_relative_to(self.settings.scratch.resolve()):
            shutil.rmtree(path, ignore_errors=True)

    def _copy_tree(self, source: Path, destination: Path) -> None:
        budget = CopyBudget(self.settings.limits)
        for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
            here = Path(dirpath)
            base = here.relative_to(source)
            dirnames[:] = [name for name in dirnames if self._keeps_directory(here, base, name)]
            (destination / base).mkdir(parents=True, exist_ok=True)
            for name in filenames:
                if self._keeps_file(here / name, base):
                    budget.charge((here / name).stat().st_size)
                    shutil.copyfile(here / name, destination / base / name)

    @staticmethod
    def _keeps_directory(here: Path, base: Path, name: str) -> bool:
        return not (name in SKIPPED_NAMES or (here / name).is_symlink()
                    or (name == ".git" and base != TOP)         # only the clone's own .git ...
                    or (name == "hooks" and base == GIT))       # ... and never its hooks

    @classmethod
    def _keeps_file(cls, path: Path, base: Path) -> bool:
        if path.name in SKIPPED_NAMES or path.is_symlink() or not path.is_file():
            return False
        if base == GIT and path.name == "config":
            return False                                # replaced by the safe one
        return not (base == TOP and path.name in GENERATED_VERDICT_NAMES and cls._is_ours(path))      # claude judges the project afresh

    @staticmethod
    def _is_ours(path: Path) -> bool:
        try:
            return path.read_bytes()[:200].startswith(VERDICT_MARKER.encode())
        except OSError:
            return False

    def _git_config(self, source: Path) -> str:
        url = self._origin_url(source) if self.settings.ssh_auth_sock else None     # a remote is only useful when you can push
        return SAFE_GIT_CONFIG + (f'[remote "origin"]\n\turl = {url}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n' if url else "")

    def _origin_url(self, source: Path) -> str | None:
        """The clone's `origin`, read as data by `git config --file` (which runs nothing), and only if it is an ordinary address."""
        config = source / GIT / "config"
        if config.is_symlink() or not config.is_file():
            return None
        try:
            done = subprocess.run(["git", "config", "--file", str(config), "--get", "remote.origin.url"], capture_output=True, text=True,
                                  timeout=5, env={**self.environment.plain(), "GIT_CONFIG_NOSYSTEM": "1"}, stdin=subprocess.DEVNULL)
        except (subprocess.TimeoutExpired, OSError):
            return None
        url = done.stdout.strip()
        return url if done.returncode == 0 and SAFE_REMOTE_URL.fullmatch(url) else None
