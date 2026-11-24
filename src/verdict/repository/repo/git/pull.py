"""Pulling a project the user already has: fast-forward only, and never with a configuration that could run something."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from verdict.repository.repo.address.urls import validate_url
from verdict.repository.repo.git.client import GitClient
from verdict.repository.repo.git.failures import explain_clone_failure
from verdict.repository.repo.git.inspector import FolderInspector
from verdict.repository.repo.model.errors import RepoError
from verdict.repository.repo.model.records import RepoInfo

# The only settings a repository's own .git/config may hold before it is pulled. claude and the shell can write to the
# projects folder, so anything else (core.sshCommand, core.fsmonitor, a filter driver, an include, ...) could run a command
# here, in the container that has your ssh-agent. A plain clone only has these.
PULL_SAFE_CONFIG = re.compile(
    r"core\.(repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|precomposeunicode|symlinks)"
    r"|remote\.[^\s]+\.(url|fetch|pushurl|prune|tagopt)"
    r"|branch\.[^\s]+\.(remote|merge|rebase)"
    r"|submodule\.[^\s]+\.(url|active)"
    r"|user\.(name|email)|pull\.(rebase|ff)|init\.defaultbranch"
)


class Puller:
    """Template Method: check the folder, read its own configuration, check the remotes, pull (through the ssh-agent)."""

    TIMEOUT = 300
    SETTINGS = ("protocol.allow=never", "protocol.ssh.allow=always")

    def __init__(self, client: GitClient, inspector: FolderInspector) -> None:
        self.client, self.inspector = client, inspector

    def _git(self, folder: Path, *args: str, timeout: int = 20) -> subprocess.CompletedProcess:
        try:
            return self.client.run(*args, folder=folder, config=self.SETTINGS, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RepoError(f"git {args[0]} timed out after {timeout}s") from exc

    def _settings(self, folder: Path) -> list[tuple[str, str]]:
        """The (key, value) of the repository's own configuration. --local reads only .git/config and does not follow includes,
        so an include shows up as a key and is refused."""
        listing = self._git(folder, "config", "--local", "--list").stdout.splitlines()
        return [(key, value) for key, _, value in (line.partition("=") for line in listing if line)]

    def pull(self, folder: Path) -> tuple[RepoInfo, str]:
        """Fast-forward `folder` to its upstream (git pull --ff-only). Returns the new state and git's summary."""
        if not (folder / ".git").is_dir():
            raise RepoError("This folder is not a git repository, so there is nothing to pull.")
        config = self._settings(folder)
        unsafe = sorted({key for key, _ in config if not PULL_SAFE_CONFIG.fullmatch(key)})
        if unsafe:
            raise RepoError(f"Not pulling: .git/config has settings that could run commands ({', '.join(unsafe[:5])}). "
                            "Pull from your own terminal after checking them.")
        urls = [value for key, value in config if re.fullmatch(r"remote\..+\.url", key)]
        if not urls:
            raise RepoError("This repository has no remote to pull from.")
        for url in urls:   # every remote, since the branch may track one other than origin
            validate_url(url)
        proc = self._git(folder, "pull", "--ff-only", "--no-recurse-submodules", timeout=self.TIMEOUT)
        if proc.returncode != 0:
            raise RepoError(explain_clone_failure(proc.stderr, proc.returncode).replace("git clone failed", "git pull failed", 1))
        lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        return self.inspector.info(folder), (lines[-1] if lines else "Already up to date.")


def pull(path: Path, known_hosts: Path) -> tuple[RepoInfo, str]:
    """Fast-forward `path` to its upstream (git pull --ff-only), through the ssh-agent. Returns the new state and git's summary."""
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    client = GitClient.networked(known_hosts, global_config=False)
    return Puller(client, FolderInspector(GitClient.offline())).pull(path)
