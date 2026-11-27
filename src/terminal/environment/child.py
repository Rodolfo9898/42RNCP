"""The environment claude, and everything it starts, runs in."""

from __future__ import annotations

from pathlib import Path

from sandbox.display.xvfb import VirtualDisplay
from terminal.settings.settings import Settings


class ChildEnvironment:
    """Builder of the only environment claude gets: no secret from this process (no token, no API key; the one placeholder key of the
    Mac's Apple gateway is not a secret). The virtual display is the one of the sandbox (programs with a window need an X display, and
    a container has none)."""

    def __init__(self, settings: Settings, display: VirtualDisplay) -> None:
        self.settings, self.display = settings, display

    def plain(self, session_id: str = "", project: Path | None = None) -> dict[str, str]:
        """The environment without a display. `project` is the real folder claude works in."""
        settings, home = self.settings, self.settings.home
        env = {
            "PATH": settings.path,
            "HOME": home,
            "TERM": "xterm-256color",
            "LANG": "C.UTF-8",
            "CLAUDE_CONFIG_DIR": settings.claude_config_dir,
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DOCKER_CONFIG": f"{home}/.docker",
        }
        if settings.docker_host:
            env["DOCKER_HOST"] = settings.docker_host
        if settings.ssh_auth_sock:
            env["SSH_AUTH_SOCK"] = settings.ssh_auth_sock
        if settings.claude_gateway_url:              # a Mac: claude talks to Apple Claude Code's proxy (docker-compose.apple.yml), not to a login of its own
            env["ANTHROPIC_BASE_URL"] = settings.claude_gateway_url
            env["CLAUDE_GATEWAY_URL"] = settings.claude_gateway_url       # (the setting itself too: the terminal that "AI Review" opens runs
            if settings.claude_gateway_token:                              # `editor_launcher claude`, which builds this environment again from
                env["ANTHROPIC_AUTH_TOKEN"] = settings.claude_gateway_token   # what the editor gave it, and would otherwise find no gateway)
                env["CLAUDE_GATEWAY_TOKEN"] = settings.claude_gateway_token
        if subjects := settings.folders.subjects(session_id):       # where the PDFs of this review are (or will be: they may arrive later)
            env["SUBJECTS_DIR"] = str(subjects)
        if project is not None:
            self._in_project(env, session_id, project)
        return env

    def build(self, session_id: str = "", project: Path | None = None) -> dict[str, str]:
        """`plain`, plus a virtual display so that a program with a window starts."""
        return {**self.plain(session_id, project), **self.display.environment()}

    def _in_project(self, env: dict[str, str], session_id: str, project: Path) -> None:
        if reports := self.settings.folders.reports(session_id):
            env["REPORT_DIR"] = str(reports)           # claude's report goes here, not into your project
        # As far as the container can tell, your folder belongs to another user, and git refuses such a folder unless told otherwise.
        # Only this exact folder is declared safe, for this process and its children only; nothing is written to any git config.
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0=str(project))
