"""What the AI review is shown of a repository, and how untrusted text is kept from posing as instructions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Digest:
    text: str
    lines: dict[str, int]  # every included file -> its total number of lines (to validate citations)
    included: list[str] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)  # sent only in part
    omitted: list[str] = field(default_factory=list)    # not sent at all


def fence(text: str) -> str:
    """Defuse any tag we use as a delimiter (opening or closing) inside untrusted text."""
    return re.sub(r"<(/?)(file|repository|subject_item|tree)\b", r"<\\\1\2", text, flags=re.I)
