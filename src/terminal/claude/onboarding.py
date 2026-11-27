"""claude's first-run state, in its config folder."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from terminal.settings.settings import Settings

ONBOARDING_FLAG = "hasCompletedOnboarding"


class FirstRun:
    """Skips claude's first-run wizard (the theme, then "Select login method") when claude is sent to a gateway.

    With the gateway's placeholder key in its environment claude needs no login of its own, but on an empty config folder (the claude-home
    volume of a new container) it still opens the wizard, which asks for a subscription. The wizard is skipped by the flag claude sets
    itself when it is done: `hasCompletedOnboarding` in `$CLAUDE_CONFIG_DIR/.claude.json`. Only that key is added; the rest of the file,
    which claude writes, stays as it is, and a file that is not a JSON object is left alone. Without a gateway nothing is done: you log in
    the way you always did."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(settings.claude_config_dir) / ".claude.json"

    def prepare(self) -> bool:
        """True when the flag was written now. Never raises: a folder that cannot be written only leaves the wizard where it was."""
        if not self.settings.claude_gateway_url:
            return False
        state = self._read()
        if state is None or state.get(ONBOARDING_FLAG) is True:
            return False
        state[ONBOARDING_FLAG] = True
        try:
            self._write(state)
        except OSError:
            return False
        return True

    def _read(self) -> dict | None:
        """The file as a dict ({} when there is none yet); None when it is there but cannot be read as a JSON object."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _write(self, state: dict) -> None:
        """Whole or not at all: claude may read the file at any time. mkstemp makes it private to its owner (0600)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".claude.json.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(state, out, indent=2)
                out.write("\n")
            os.replace(name, self.path)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise
