"""The subject library: the PDFs in samples/<track>/."""

from fastapi import APIRouter, File, UploadFile

from verdict.api.deps import ContainerDep
from verdict.library.catalog import MAX_PDF_BYTES
from verdict.sessions.store import safe_filename

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
def listing(container: ContainerDep) -> dict:
    return container.library.listing()


@router.post("/{track}/subjects", status_code=201)
async def upload(track: str, container: ContainerDep, files: list[UploadFile] = File(...)) -> dict:
    """Keep uploaded PDFs in the library folder of their track (an existing file with other content is never replaced)."""
    items = []
    for pdf in files:
        data = await pdf.read(MAX_PDF_BYTES + 1)
        items.append(container.library.upload(track, safe_filename(pdf.filename or "subject.pdf"), data))
    return {"items": items}
