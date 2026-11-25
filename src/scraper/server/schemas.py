"""The bodies the routes accept."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Name = Annotated[str, StringConstraints(min_length=1, max_length=120)]       # a track, or a project as a person names it


class DownloadRequest(BaseModel):
    """What to download: some tracks and/or some projects (null: all), whether the artifacts come too, and whether to do it again."""

    tracks: Annotated[list[Name], Field(max_length=10)] | None = None
    projects: Annotated[list[Name], Field(max_length=500)] | None = None
    artifacts: bool = True
    children: bool = True
    force: bool = False


class ReorganizationRequest(BaseModel):
    dry_run: bool = True          # looking is the default; moving needs `false`
