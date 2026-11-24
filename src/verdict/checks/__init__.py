"""The check engine: runs every rule of a session against a cloned repository.

Layout: `context` (what a checker is handed: files, folders to build, sandbox), `engine` (the Checker base class), `dispatch` (the
registry of checkers by rule kind, and the run), and the checkers themselves by what they look at: `files`, `make` (what runs make), `functions`,
`norm`, `source`, `repo`, `runtime`. This module is the public face: the web app imports its names from here.
"""

from shared.constants import GENERATED_VERDICT_NAMES, VERDICT_MARKER
from verdict.checks.context.ctx import Ctx
from verdict.checks.context.vendored import EXCLUDED_DIRS, minilibx_dirs
from verdict.checks.dispatch.runner import run_checks
from verdict.checks.source.text import strip_code

__all__ = ["Ctx", "EXCLUDED_DIRS", "GENERATED_VERDICT_NAMES", "VERDICT_MARKER", "minilibx_dirs", "run_checks", "strip_code"]
