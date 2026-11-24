"""The one place that builds the environment git runs in and runs git."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

Runner = Callable[..., subprocess.CompletedProcess]

SSH_OPTIONS = "ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new"


class GitClient:
    """Facade over the git command line, with two kinds of environment (named constructors).

    The environment is built from nothing but what git needs, never from ours (no token of the app can leak into a command run on
    an untrusted repository): `networked` talks to remote servers through the forwarded ssh-agent (the private key never enters this
    container) and remembers host keys in the workspace; `offline` only reads folders on disk. Any command run on a folder is told
    to ignore what that folder's own configuration would run (hooks, fsmonitor) and that the folder is safe to read.
    """

    def __init__(self, env: Mapping[str, str], runner: Runner = subprocess.run) -> None:
        self.env = dict(env)
        self.runner = runner

    @classmethod
    def networked(cls, known_hosts: Path, *, global_config: bool = True, protocols: Sequence[str] | None = None,
                  runner: Runner = subprocess.run) -> GitClient:
        """`known_hosts`: where SSH host keys are remembered (its folder is HOME). `global_config`: False to ignore ~/.gitconfig.
        `protocols`: the only protocols git may use for submodules (GIT_ALLOW_PROTOCOL), when given."""
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(known_hosts.parent),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            **({} if global_config else {"GIT_CONFIG_GLOBAL": "/dev/null"}),
            "GIT_LFS_SKIP_SMUDGE": "1",
            **({"GIT_ALLOW_PROTOCOL": ":".join(protocols)} if protocols is not None else {}),
            "GIT_SSH_COMMAND": f"{SSH_OPTIONS} -o UserKnownHostsFile={known_hosts}",
        }
        if os.environ.get("SSH_AUTH_SOCK"):  # the forwarded agent: the private key never enters this container
            env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        return cls(env, runner)

    @classmethod
    def offline(cls, runner: Runner = subprocess.run) -> GitClient:
        return cls({"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0"}, runner)

    @property
    def has_agent(self) -> bool:
        return bool(self.env.get("SSH_AUTH_SOCK"))

    @staticmethod
    def folder_settings(folder: Path) -> list[str]:
        """What stops a folder's own configuration from running anything while git reads it."""
        return [f"safe.directory={folder}", "core.fsmonitor=false", "core.hooksPath=/dev/null"]

    def command(self, args: Sequence[str], *, folder: Path | None = None, config: Sequence[str] = ()) -> list[str]:
        settings = [*(self.folder_settings(folder) if folder else ()), *config]
        return ["git", *(a for setting in settings for a in ("-c", setting)), *(["-C", str(folder)] if folder else []), *args]

    def run(self, *args: str, folder: Path | None = None, config: Sequence[str] = (), timeout: float = 20) -> subprocess.CompletedProcess:
        """`git <args>` (in `folder`, when given), with `config` as extra `-c` settings. subprocess.TimeoutExpired is left to the caller."""
        return self.runner(self.command(args, folder=folder, config=config), env=self.env, capture_output=True, text=True,
                           timeout=timeout, check=False)
