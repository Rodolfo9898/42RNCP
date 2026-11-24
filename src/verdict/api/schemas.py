"""What a client sends."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


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
