"""Everything the terminal service reads from its environment, read once at start and handed to whoever needs it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from shared.constants import TERMINAL_REPORTS_ROOT, TERMINAL_SUBJECTS_ROOT
from terminal.settings.editor import EditorSettings
from terminal.settings.folders import SessionFolders
from terminal.settings.limits import Limits


@dataclass(frozen=True)
class Settings:
    """The one settings object: created by the composition root (`from_environment`), injected everywhere, never read from os.environ
    again. Claude always works in the project folder (under `projects`); `scratch` only holds the copies the headless review reads."""

    projects: Path
    scratch: Path
    claude: str                      # the claude executable
    home: str
    token: str                       # the secret shared with the web app ("" = every request is refused)
    folders: SessionFolders
    editor: EditorSettings
    claude_config_dir: str           # where claude keeps its login and settings
    path: str = "/usr/local/bin:/usr/bin:/bin"
    docker_host: str = ""            # the separate daemon (never the host's), passed on only if the operator set one
    ssh_auth_sock: str = ""          # your ssh-agent, only when docker-compose.ssh.yml mounted it (see the README)
    claude_gateway_url: str = ""     # where claude sends its requests instead of Anthropic: only on a Mac, docker-compose.apple.yml (see the README)
    claude_gateway_token: str = ""   # the placeholder key that gateway wants (not a secret: the gateway adds the real sign-in)
    limits: Limits = field(default_factory=Limits)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> Settings:
        home = environ.get("TERMINAL_HOME", "/home/term")
        projects = Path(environ.get("PROJECTS_DIR", "/projects"))
        return cls(
            projects=projects,
            scratch=Path(environ.get("SCRATCH_DIR", "/scratch")),
            claude=environ.get("CLAUDE_BIN", "claude"),
            home=home,
            token=environ.get("TERMINAL_TOKEN", ""),
            folders=SessionFolders(Path(environ.get("SUBJECTS_ROOT", TERMINAL_SUBJECTS_ROOT)),
                                   Path(environ.get("REPORTS_ROOT", TERMINAL_REPORTS_ROOT))),
            editor=EditorSettings.from_environment(environ, home, projects),
            path=environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            claude_config_dir=environ.get("CLAUDE_CONFIG_DIR", f"{home}/.claude"),
            docker_host=environ.get("DOCKER_HOST", ""),
            ssh_auth_sock=environ.get("SSH_AUTH_SOCK", ""),
            claude_gateway_url=environ.get("CLAUDE_GATEWAY_URL", ""),
            claude_gateway_token=environ.get("CLAUDE_GATEWAY_TOKEN", ""),
        )

    @property
    def ssh_agent_ready(self) -> bool:
        """Was this container given your ssh-agent (docker-compose.yml's ssh override, TERMINAL_SSH=1)? Without it git cannot sign in over ssh."""
        return bool(self.ssh_auth_sock) and Path(self.ssh_auth_sock).exists()
