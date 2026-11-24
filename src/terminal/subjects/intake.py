"""Checking the PDFs a review hands over, before anything is stored."""

from fastapi import UploadFile

from shared.constants import is_subject_name
from terminal.settings.limits import Limits


class SubjectRefused(ValueError):
    """The handover is not acceptable (the message says why); nothing was stored."""


class SubjectIntake:
    """Reads the uploaded PDFs into memory, within the limits, and refuses anything that is not a PDF with a plain name. The PDFs are
    untrusted data: they are never opened here, only checked for their first bytes and stored."""

    def __init__(self, limits: Limits) -> None:
        self.limits = limits

    async def collect(self, uploads: list[UploadFile]) -> dict[str, bytes]:
        """{name: bytes} of all of them, or SubjectRefused."""
        limits = self.limits
        if len(uploads) > limits.max_subject_files:
            raise SubjectRefused(f"at most {limits.max_subject_files} PDFs")
        received: dict[str, bytes] = {}
        total = 0
        for upload in uploads:
            name = upload.filename or ""
            data = await upload.read(limits.max_subject_file_bytes + 1)
            total += len(data)
            if not is_subject_name(name) or name in received:
                raise SubjectRefused(f"not an acceptable PDF name: {name!r}")
            if not data.startswith(b"%PDF") or len(data) > limits.max_subject_file_bytes or total > limits.max_subject_total_bytes:
                raise SubjectRefused(f"{name} is not a PDF, or is too large")
            received[name] = data
        return received
