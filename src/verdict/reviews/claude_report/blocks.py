"""Finding the structured block at the end of claude's report."""

from __future__ import annotations

import json
import re


def fenced_blocks(markdown: str) -> list[tuple[str, str]]:
    """(language, body) of every fenced code block, reading line by line so that a closing fence is never mistaken
    for the opening of the next block (claude's prose usually has other code blocks before the json)."""
    blocks: list[tuple[str, str]] = []
    opener = ""            # the fence characters that opened the current block ("" outside one)
    language, body = "", []
    for line in markdown.splitlines():
        stripped = line.strip()
        marker = re.match(r"(`{3,}|~{3,})(.*)$", stripped)
        if not opener:
            if marker:
                opener, language, body = marker.group(1), marker.group(2).strip().lower(), []
        elif marker and marker.group(1)[0] == opener[0] and len(marker.group(1)) >= len(opener) and not marker.group(2).strip():
            blocks.append((language, "\n".join(body)))
            opener = ""
        else:
            body.append(line)
    return blocks                      # an unclosed block at the end is not data


def extract_block(markdown: str) -> dict | None:
    """The last json block that looks like the report data."""
    for language, body in reversed(fenced_blocks(markdown)):
        if language not in ("", "json", "jsonc"):
            continue
        try:
            data = json.loads(body)
        except ValueError:
            continue
        if isinstance(data, dict) and ("items" in data or "verdict" in data or "fixes" in data):
            return data
    return None
