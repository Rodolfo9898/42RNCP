"""What the web app and the terminal container have to agree on: where a review's subject PDFs and claude's report are kept inside the
terminal container, what a subject PDF may be called, and which files never reach claude's copy."""

from __future__ import annotations

import re

# Where the terminal container keeps the PDFs of a review (one folder per web session), and what a PDF of a subject may be called.
TERMINAL_SUBJECTS_ROOT = "/scratch/subjects"
# Where claude saves its report when it works in the project folder itself: the report must not become a file of your project.
TERMINAL_REPORTS_ROOT = "/scratch/reports"
SUBJECT_NAME = re.compile(r"\w[\w.\- ]{0,118}\.pdf", re.IGNORECASE)


def is_subject_name(name: str) -> bool:
    return bool(SUBJECT_NAME.fullmatch(name)) and ".." not in name


# Files that configure or instruct claude. A scratch copy is made without them: a repository is untrusted, and these would let it
# instruct (or run hooks of) the claude that opens it.
SKIPPED_NAMES = {".claude", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md", ".claude.json"}
