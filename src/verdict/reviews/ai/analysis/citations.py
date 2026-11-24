"""Checking what the model cites against what it was shown."""

from __future__ import annotations

from verdict.core.models import Evidence
from verdict.reviews.ai.analysis.models import CitationOut
from verdict.reviews.digest import Digest


class CitationVerifier:
    """Keeps only citations of files and lines that were actually shown to the model: an invented location is dropped."""

    def __init__(self, digest: Digest):
        self.digest = digest

    def verified(self, citations: list[CitationOut], limit: int = 5) -> list[Evidence]:
        out: list[Evidence] = []
        for c in citations:
            file = c.file.strip().lstrip("./")
            total = self.digest.lines.get(file)
            if total is not None and 1 <= c.line <= total:
                out.append(Evidence(file=file, line=c.line))
            if len(out) >= limit:
                break
        return out


def verified(citations: list[CitationOut], digest: Digest, limit: int = 5) -> list[Evidence]:
    return CitationVerifier(digest).verified(citations, limit)
