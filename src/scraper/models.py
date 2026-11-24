"""Plain data objects shared between the layers."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Link:
    url: str
    text: str


@dataclass
class ParsedPage:
    h1: str = ""
    title: str = ""
    links: list[Link] = field(default_factory=list)


@dataclass(frozen=True)
class FileLink:
    """A downloadable file found on a project page."""

    url: str
    text: str
    filename: str

    @property
    def ext(self) -> str:
        return Path(self.filename).suffix.lower()

    @property
    def is_subject(self) -> bool:
        return self.ext == ".pdf" and (
            "subject" in self.filename.lower() or "subject" in self.text.lower() or "/pdf/" in urlparse(self.url).path)

    @property
    def lang(self) -> str:
        m = re.match(r"([a-z]{2})[._\-]", self.filename.lower())
        return m.group(1) if m else ""


@dataclass(frozen=True)
class ProjectInfo:
    """What a project page offers: its subject PDF(s) and the other files (artifacts)."""

    slug: str
    name: str
    subjects: list[FileLink]
    artifacts: list[FileLink]


@dataclass
class Stats:
    counts: Counter = field(default_factory=Counter)
    no_files: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
