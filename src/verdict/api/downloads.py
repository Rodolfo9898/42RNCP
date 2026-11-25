"""Getting the subjects the library lacks from the 42 intra (through the scraper service), and filing them in the folders of their series."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from verdict.api.deps import ContainerDep
from verdict.api.schemas import DownloadRequest, ReorganizationRequest, Track
from verdict.library.catalog import TRACKS

router = APIRouter(prefix="/api/library", tags=["downloads"])


@router.get("/plan")
def plan(container: ContainerDep, track: Annotated[list[Track] | None, Query(max_length=len(TRACKS))] = None, children: bool = True) -> dict:
    """What each track lacks, and `ready`: whether the saved intra session can download it. No track: all three."""
    return container.downloads.plan(track or [], children)


@router.post("/downloads", status_code=202)
def start(request: DownloadRequest, container: ContainerDep) -> dict:
    """Start downloading in the background (one download at a time): 400 when the session is not usable, 409 when one is running."""
    return container.downloads.start(**request.model_dump())


@router.get("/downloads/current")
def current(container: ContainerDep, since: Annotated[int, Query(ge=0)] = 0) -> dict:
    """The state of the download and its log lines from number `since` on (`next` is the number to ask for next time)."""
    return container.downloads.current(since)


@router.delete("/downloads/current")
def cancel(container: ContainerDep) -> dict:
    """A running download stops between two projects."""
    return container.downloads.cancel()


@router.post("/reorganizations")
def reorganize(container: ContainerDep, request: Annotated[ReorganizationRequest, Body(default_factory=ReorganizationRequest)]) -> dict:
    """File what is already in samples/ and artifacts/ into the folders of its series. Without a body: only list the moves."""
    return container.downloads.reorganize(request.dry_run)
