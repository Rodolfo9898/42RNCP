"""The argument lists of the two ways claude is started."""

from __future__ import annotations

import json

from terminal.claude.prompts import APPEND_PROMPT, APPEND_PROMPT_LIVE


class ClaudeCommand:
    """Builder of claude's argv. Both ways carry the same protections: no settings, hooks or MCP servers from the repository."""

    def __init__(self, executable: str) -> None:
        self.executable = executable

    def version(self) -> list[str]:
        return [self.executable, "--version"]

    def interactive(self, prompt: str | None = None) -> list[str]:
        """claude's interactive UI in the project folder (the editor's terminal); an initial prompt (the review request) is its last,
        positional argument."""
        # readpdf only prints PDFs of the review and writes nothing, so asking before each use would only invite a script instead.
        # (Listed first: the list of tools ends at the next option, which is why the prompt, a plain argument, must stay last.)
        return [self.executable, "--allowedTools", "Bash(readpdf:*)", *self._safe_flags(APPEND_PROMPT_LIVE)] + ([prompt] if prompt else [])

    def review(self, prompt: str, schema: dict, model: str | None) -> list[str]:
        """`claude -p` for the one-click review, on a copy: investigation only, nothing to approve."""
        argv = [
            self.executable, "-p", prompt, "--output-format", "json", "--json-schema", json.dumps(schema),
            "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob",
            "--permission-mode", "dontAsk", "--no-session-persistence", *self._safe_flags(APPEND_PROMPT),
        ]
        return argv + (["--model", model] if model else [])

    @staticmethod
    def _safe_flags(system_prompt: str) -> list[str]:
        return [
            "--setting-sources", "user",     # never read settings (hooks!) shipped inside the repository
            "--strict-mcp-config",           # nor MCP servers
            "--append-system-prompt", system_prompt,
        ]
