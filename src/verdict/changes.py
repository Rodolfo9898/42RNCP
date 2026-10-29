"""What may travel from a working copy back to the project, and which paths are acceptable.

The terminal container reports what changed in its throw-away copy; the web app, which owns the projects folder, writes what
the user approves. Both sides apply these rules, so a wrong answer from one of them is not enough to write something bad.
"""

from __future__ import annotations

# Files that configure or instruct claude. The copy is made without them, and they never go back: an agent that could write
# them into your project would be instructing the next claude (or its hooks) that opens it on your machine.
SKIPPED_NAMES = {".claude", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md", ".claude.json"}
# Folders an editor or shell may run things from. They go back only if the user ticks them after reading them.
RISKY_PARTS = {".vscode", ".devcontainer", ".idea", ".cursor", ".husky", ".githooks", ".envrc", ".direnv"}


def is_plain_path(rel: str) -> bool:
    """A relative path made of ordinary names: no `..`, no absolute path, no backslash or NUL, no empty parts."""
    return bool(rel) and not rel.startswith("/") and "\\" not in rel and "\0" not in rel and not any(part in ("", ".", "..") for part in rel.split("/"))


def change_policy(rel: str) -> tuple[str, str]:
    """(why this path is never sent back, why it needs a second look) for a path inside the project."""
    parts = rel.split("/")
    if not is_plain_path(rel):
        return "not a plain path inside the project", ""
    if any(part == ".git" or part in SKIPPED_NAMES for part in parts):
        return "never sent back: it would configure git or claude on your machine", ""
    if RISKY_PARTS.intersection(parts):
        return "", "an editor or shell may run what is in here: read it before you apply it"
    return "", ""
