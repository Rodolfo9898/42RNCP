"""What the web app and the terminal container have to agree on: who the evaluator is, where a review's subject PDFs and claude's
report are kept inside the terminal container, what a subject PDF may be called, and which files never reach claude's copy."""

from __future__ import annotations

import re

# Who is using this app, so that claude knows whom it works for (its system prompt and the review prompt say so).
EVALUATOR = "rperez-t"
# The Norm wants the 42 header at the top of every C file, with the author as `By: login <email>`: this is what a new file gets.
EVALUATOR_EMAIL = "rperez-t@student.42belgium.be"
HEADER_AUTHOR = f"{EVALUATOR} <{EVALUATOR_EMAIL}>"

# Where the terminal container keeps the PDFs of a review (one folder per web session), and what a PDF of a subject may be called.
TERMINAL_SUBJECTS_ROOT = "/scratch/subjects"
# Where claude saves its report when it works in the project folder itself: the report must not become a file of your project.
TERMINAL_REPORTS_ROOT = "/scratch/reports"
SUBJECT_NAME = re.compile(r"\w[\w.\- ]{0,118}\.pdf", re.IGNORECASE)


def is_subject_name(name: str) -> bool:
    return bool(SUBJECT_NAME.fullmatch(name)) and ".." not in name


# Where claude tries the project: in the folder it was started in. A copy in /tmp is not the project (other files, other build
# output, a different path) and a test run there proves little, so every prompt says to build, run and test right here.
TEST_HERE = ("Build, run and test in the current directory, which is the project: never copy the project to /tmp or to any other "
             "folder to try it, and do not cd out of it to build. Scratch files (inputs, outputs, logs) go inside the current "
             "directory too, and you remove them when you are done.")

# Files that configure or instruct claude. A scratch copy is made without them: a repository is untrusted, and these would let it
# instruct (or run hooks of) the claude that opens it.
SKIPPED_NAMES = {".claude", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md", ".claude.json"}
