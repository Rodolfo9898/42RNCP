"""The words a subject's tables are labelled with, and the chapters whose prose holds no requirement."""

from __future__ import annotations

LABELS = {
    "program name": "program",
    "files to submit": "files",
    "turn in files": "files",
    "turn-in files": "files",
    "makefile": "makefile",
    "arguments": "arguments",
    "external function": "functions",
    "external functions": "functions",
    "external functs.": "functions",
    "libft authorized": "libft",
    "description": "description",
    "function name": "function_name",
    "prototype": "prototype",
    "parameters": "parameters",
    "return value": "return_value",
}

# Chapters whose prose never contains requirements for the repository.
SKIPPED_CHAPTERS = (
    "introduction", "foreword", "preamble", "ai instructions", "objectives",
    "submission and peer", "contents", "table of contents",
)


def label_of(text: str) -> str | None:
    return LABELS.get(text.strip().rstrip(":").strip().lower())
