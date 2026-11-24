"""The sentences of the result of a `required_files` rule: what was not where the subject says, and why that is (not) a problem."""

from __future__ import annotations

from verdict.checks.files.finder import Search
from verdict.core.models import Rule


def moved_text(rule: Rule, moved: str) -> str:
    if moved == rule.unit:
        return ""
    return (f" The subject's `{rule.unit}/` folder does not exist: the project shares its code instead (DRY, which this evaluation "
            f"accepts outside libft, ft_printf and get_next_line), so its files were looked for in `{moved}/`.")


def note_text(rule: Rule) -> str:
    notes = rule.params.get("notes") or []
    return f" Not machine-checkable: {'; '.join(notes)}." if notes else ""


def elsewhere_text(search: Search, strict: bool) -> str:
    if not search.relocated:
        return ""
    if strict:
        return (f" Found elsewhere than listed: {'; '.join(search.relocated)}. If the subject lets you organise the project in subfolders "
                "this is fine; a human (or the AI review) should confirm it does.")
    return (f" Present in another place than the subject shows: {'; '.join(search.relocated)}. The layout is free in this project "
            "(only libft, ft_printf and get_next_line must follow it), so this is fine.")


def expected_text(search: Search, strict: bool) -> str:
    if not search.expected:
        return ""
    names = ', '.join(f'`{e}`' for e in search.expected)
    if strict:
        return (f" Not found, but the subject only shows these in an example layout: {names}. "
                "Whether the layout matters is for a human (or the AI review) to say.")
    return f" The subject's example layout also shows {names}; an example is not a requirement."
