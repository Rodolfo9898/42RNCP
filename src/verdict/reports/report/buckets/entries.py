"""The entries verdict.md lists, and the places they are sorted into."""

from __future__ import annotations

from dataclasses import dataclass, field

from verdict.core.models import Evidence


@dataclass
class Entry:
    title: str
    detail: str = ""
    by: str = "script"            # "script", or who assessed it: "Claude", "AI"
    sources: list = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    check_by_hand: str = ""
    log: str = ""
    requirement: bool = False     # a subject sentence (shown as plain text) rather than the title of a check


@dataclass
class Buckets:
    lacking: list[Entry] = field(default_factory=list)
    second: list[Entry] = field(default_factory=list)
    ok: list[Entry] = field(default_factory=list)
    not_applicable: list[Entry] = field(default_factory=list)
    unreviewed: list[Entry] = field(default_factory=list)       # requirements nobody has assessed yet (also part of `second`)
    not_submitted: list[Entry] = field(default_factory=list)
