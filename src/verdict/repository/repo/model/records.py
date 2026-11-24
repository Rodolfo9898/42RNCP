"""What the repository operations hand back."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RepoInfo:
    url: str
    commit: str
    subject: str
    author: str


@dataclass
class SubmoduleNote:
    path: str          # relative to the project
    ok: bool
    message: str       # why it could not be downloaded (or what was done)
