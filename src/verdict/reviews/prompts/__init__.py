"""The prompts this app writes for `claude`: one to evaluate what the scripts could not, one to fix what the review found.

Both are built from this session's own results. The review prompt lists what the checks proved so claude does not redo it, and
everything left open (requirements that need judgement, checks that could not run, and the limits no script has)
becomes the task. The fix prompt turns what verdict.md lists as lacking or worth a second look into the task.
claude works in the project folder itself, so both say where its report goes (outside the project).
"""

from verdict.reviews.prompts.docker import DOC_EXTENSIONS, find_docker_files
from verdict.reviews.prompts.fix import FIX_PROOF, FIX_RULES, MAX_LOG_CHARS, FixPromptBuilder, build_fix_prompt, issue_lines
from verdict.reviews.prompts.items import MAX_ITEM_CHARS, MAX_ITEMS, MAX_LISTED, manual_items, titles
from verdict.reviews.prompts.limits import LIMIT_WORDS, MAX_LIMITS, library_limits, limits_section
from verdict.reviews.prompts.review import UNCOVERED_BY_ANY_SCRIPT, ReviewPromptBuilder, build_review_prompt
from verdict.reviews.prompts.text import short

__all__ = [
    "DOC_EXTENSIONS", "FIX_PROOF", "FIX_RULES", "LIMIT_WORDS", "MAX_ITEMS", "MAX_ITEM_CHARS", "MAX_LIMITS", "MAX_LISTED", "MAX_LOG_CHARS",
    "UNCOVERED_BY_ANY_SCRIPT", "FixPromptBuilder", "ReviewPromptBuilder", "build_fix_prompt", "build_review_prompt", "find_docker_files",
    "issue_lines", "library_limits", "limits_section", "manual_items", "short", "titles",
]
