"""The environment of every command: clean, with a virtual display, plus the few variables a request is allowed to add."""

from __future__ import annotations

from collections.abc import Mapping

from sandbox.display.xvfb import VirtualDisplay


class CommandEnvironment:
    """Builder of the environment a command runs in. Nothing of the runner's own environment leaks into it (no token, no ssh-agent).

    The sandbox has a Docker client but no daemon. If an operator deliberately points the runner at one (DOCKER_HOST), commands run
    by the review can use it; nothing is passed on otherwise (and the host's socket is never mounted)."""

    def __init__(self, display: VirtualDisplay, docker_host: str = "") -> None:
        self.display = display
        self.base = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "TMPDIR": "/tmp",
            "DOCKER_CONFIG": "/tmp/.docker",
        }
        if docker_host:
            self.base["DOCKER_HOST"] = docker_host

    @classmethod
    def from_environment(cls, environ: Mapping[str, str], display: VirtualDisplay) -> CommandEnvironment:
        return cls(display, environ.get("DOCKER_HOST", ""))

    def build(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        return {**self.base, **self.display.environment(), **(extra or {})}
