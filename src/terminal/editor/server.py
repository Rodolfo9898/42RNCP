"""VS Code in the browser (OpenVSCode Server), as a child process of the terminal container."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from terminal.environment.child import ChildEnvironment
from terminal.settings.editor import EditorSettings


class EditorServer:
    """Starts the editor with claude's environment: no token, no secret of the service."""

    def __init__(self, settings: EditorSettings, reports_root: Path, environment: ChildEnvironment,
                 token_path: Path = Path("/tmp/editor-token")) -> None:
        self.settings, self.reports_root, self.child, self.token_path = settings, reports_root, environment, token_path

    def available(self) -> bool:
        return self.settings.server.exists()

    def environment(self) -> dict[str, str]:
        """What VS Code, and every terminal opened in it, gets: claude's environment (no token, no secret of the service), a shell,
        the address of the web app and the folder of claude's reports for the Verdict extension, and git allowed in the projects
        folder (it belongs to your user on the host, which git inside a container may see as someone else)."""
        settings = self.settings
        env = self.child.build()
        env.update(SHELL=settings.shell, VERDICT_API=settings.verdict_api,
                   REPORTS_ROOT=str(self.reports_root),      # where claude saves its report: the Verdict extension merges it when it appears
                   GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0="*")
        if settings.zdotdir:
            env["ZDOTDIR"] = settings.zdotdir
        return env

    def write_default_settings(self) -> None:
        """The settings the editor starts with (machine level: what you change in Settings wins over them)."""
        machine = self.settings.data / "data" / "Machine"
        try:
            machine.mkdir(parents=True, exist_ok=True)
            (machine / "settings.json").write_text(self.settings.default_settings.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            print(f"editor: default settings not written: {exc}", file=sys.stderr)

    def start(self) -> subprocess.Popen:
        settings = self.settings
        token = self._token_file()
        argv = [str(settings.server), "--host", "0.0.0.0", "--port", settings.port, "--server-data-dir", str(settings.data),
                "--extensions-dir", str(settings.extensions), "--default-folder", settings.folder, "--telemetry-level", "off"]
        argv += ["--connection-token-file", str(token)] if token else ["--without-connection-token"]
        return subprocess.Popen(argv, env=self.environment(), start_new_session=True)

    def _token_file(self) -> Path | None:
        """The connection token, in a file only this user reads: the browser must open the editor with ?tkn=<it> once."""
        if not self.settings.token:
            return None
        self.token_path.write_text(self.settings.token, encoding="utf-8")
        self.token_path.chmod(0o600)
        return self.token_path
