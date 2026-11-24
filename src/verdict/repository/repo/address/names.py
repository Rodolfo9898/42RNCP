"""What a project or a folder of the projects folder may be called."""

from __future__ import annotations

import re

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def default_name(url: str) -> str:
    last = re.split(r"[/:]", url.strip().rstrip("/"))[-1]
    last = last[:-4] if last.endswith(".git") else last
    return last if NAME_RE.match(last) else "project"
