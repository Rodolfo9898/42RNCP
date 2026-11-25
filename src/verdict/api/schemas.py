"""What a client sends."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from verdict.library.catalog import TRACKS


class SubjectPicks(BaseModel):
    paths: list[str]                                   # library paths: `common-core/libft.pdf`


class CloneSource(BaseModel):
    kind: Literal["clone"]
    url: str
    name: str = ""
    destination: str = ""


class ExistingSource(BaseModel):
    kind: Literal["existing"]
    path: str


RepoSource = Annotated[CloneSource | ExistingSource, Field(discriminator="kind")]


class ClaudeReviewRequest(BaseModel):
    force: bool = False                                # adopt whatever claude saved, even a report asked for by another review


Track = Literal[*TRACKS]                               # common-core, post-common-core, rncp
MAX_PROJECTS, MAX_PROJECT_CHARS = 200, 100


def printable(token: str) -> str:
    """A project is named by its slug, name or id: text, never blank, never a control character (they end up in a log and a URL)."""
    if not token.strip() or not token.isprintable():
        raise ValueError("a project is named by printable characters (its slug, name or id)")
    return token


ProjectToken = Annotated[str, StringConstraints(min_length=1, max_length=MAX_PROJECT_CHARS), AfterValidator(printable)]


class DownloadRequest(BaseModel):
    """What to download from the intra. A list that is not null names something: nothing named (null) is everything the library lacks;
    a field this model does not know is refused rather than ignored (a typo must not turn a selection into a download of everything)."""

    model_config = ConfigDict(extra="forbid")

    tracks: Annotated[list[Track], Field(min_length=1, max_length=len(TRACKS))] | None = None
    projects: Annotated[list[ProjectToken], Field(min_length=1, max_length=MAX_PROJECTS)] | None = None
    artifacts: bool = True                             # the files that come with a project can be gigabytes
    children: bool = True                              # the projects inside a piscine or a series
    force: bool = False                                # download again what is already there


class ReorganizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True                               # only list the moves
