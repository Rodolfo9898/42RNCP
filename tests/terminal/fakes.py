"""Stand-ins and helpers for the terminal tests."""

import json
from pathlib import Path

TOKEN = "t0ken-for-tests"
HEADERS = {"x-terminal-token": TOKEN}

STUB = """#!/bin/sh
case "$1" in
  -p)
    echo "{\\"result\\": \\"reviewed\\", \\"args\\": \\"$*\\"}"
    exit 0 ;;
esac
echo "ARGS: $*"
"""


class FakeDisplay:
    """Stands for the virtual X display: the environment it adds, and whether it was stopped. (The real one is tested in tests/sandbox.)"""

    def __init__(self, env=None):
        self.env, self.stopped = env or {}, False

    def environment(self):
        return dict(self.env)

    def stop(self):
        self.stopped = True


def environment_of(tmp_path, **overrides):
    """What the container's environment would hold, pointing at folders of the test; and secrets that must never reach claude."""
    return {
        "PROJECTS_DIR": str(tmp_path / "projects"), "SCRATCH_DIR": str(tmp_path / "scratch"), "TERMINAL_HOME": str(tmp_path / "home"),
        "CLAUDE_BIN": str(tmp_path / "claude-stub"), "SUBJECTS_ROOT": str(tmp_path / "subjects"), "REPORTS_ROOT": str(tmp_path / "reports"),
        "TERMINAL_TOKEN": TOKEN, "ANTHROPIC_API_KEY": "sk-must-not-leak", "LLM_API_KEY": "x", "EDITOR_TOKEN": "editor-secret",
        "OPENVSCODE_SERVER": str(tmp_path / "no-editor"), "EDITOR_DATA_DIR": str(tmp_path / "editor-data"),
        "EDITOR_EXTENSIONS_LIST": str(tmp_path / "config" / "extensions.txt"), "EDITOR_DEFAULT_SETTINGS": str(tmp_path / "defaults.json"),
        "PATH": "/usr/local/bin:/usr/bin:/bin", **overrides,
    }


def manifest(folder: Path, *ids: str) -> None:
    """The extensions.json VS Code keeps in its extensions folder."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "extensions.json").write_text(json.dumps([{"identifier": {"id": i}, "version": "1.0.0", "relativeLocation": f"{i}-1.0.0"} for i in ids]))
