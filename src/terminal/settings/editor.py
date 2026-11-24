"""What the editor (VS Code in the browser) is started with."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EditorSettings:
    server: Path                 # the OpenVSCode Server executable
    data: Path                   # its data (settings, extensions)
    extensions_list: Path        # config/extensions.txt
    default_settings: Path       # the settings the editor starts with
    port: str
    folder: str                  # the folder it opens: the projects
    shell: str
    verdict_api: str
    zdotdir: str
    token: str                   # the connection token ("" = none)
    watch_seconds: int = 10      # how often the installed extensions are compared with the list
    service_port: int = 8002     # the terminal service, run in the editor's process

    @property
    def extensions(self) -> Path:
        return self.data / "extensions"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str], home: str, projects: Path) -> EditorSettings:
        data = Path(environ.get("EDITOR_DATA_DIR", str(Path(home) / ".openvscode-server")))
        return cls(
            server=Path(environ.get("OPENVSCODE_SERVER", "/opt/openvscode-server/bin/openvscode-server")),
            data=data,
            extensions_list=Path(environ.get("EDITOR_EXTENSIONS_LIST", "/config/extensions.txt")),
            default_settings=Path(environ.get("EDITOR_DEFAULT_SETTINGS", "/etc/verdict-editor/settings.json")),
            port=environ.get("EDITOR_PORT", "3000"),
            folder=environ.get("PROJECTS_DIR", str(projects)),
            shell=environ.get("TERMINAL_SHELL", "/bin/bash"),
            verdict_api=environ.get("VERDICT_API", "http://web:8000"),
            zdotdir=environ.get("ZDOTDIR", ""),
            token=environ.get("EDITOR_TOKEN", "").strip(),
        )
