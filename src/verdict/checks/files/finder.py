"""Looking for the files a subject lists, where the project has them."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from verdict.checks.context.build_result import BuildResult
from verdict.checks.context.ctx import Ctx
from verdict.core.models import Rule
from verdict.gateways.sandbox import SandboxError


class FileFinder:
    """Finds what one pattern of the subject names (a file, a wildcard, a folder when it ends with `/`) in a unit of the repository,
    and where else in the project the same name sits."""

    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx

    @staticmethod
    def anywhere(pattern: str) -> str | None:
        """`*/*.c` (or `**/*.c`) names a wildcard whose folder does not matter: the bare `*.c`, else None."""
        *folders, name = pattern.split("/")
        return name if folders and all(f in ("*", "**") for f in folders) and any(c in name for c in "*?[") else None

    def find(self, unit: str, pattern: str, *, root_only: bool = False) -> list[Path]:
        """What `pattern` names in the unit: files, or a folder when it ends with `/`. `root_only`: a wildcard counts only at the root.
        Outside the strict projects a wildcard counts in any subfolder (`*/*.h` is met by include/x.h or include/sub/x.h)."""
        ctx = self.ctx
        base = ctx.unit_dir(unit)
        folder = pattern.endswith("/")
        pattern = pattern.rstrip("/") if folder else pattern
        if not ctx.strict_layout and (bare := self.anywhere(pattern)):
            pattern = bare
        if "/" in pattern:
            hits = base.glob(pattern)
        elif any(c in pattern for c in "*?["):
            hits = base.glob(pattern) if root_only else base.rglob(pattern)
        else:
            hits = [base / pattern]
        out = []
        for p in hits:
            rel = p.relative_to(ctx.repo.resolve()).as_posix() if p.is_relative_to(ctx.repo.resolve()) else ""
            if rel and not p.is_symlink() and (p.is_dir() if folder else p.is_file()) and not ctx.is_vendored(rel + ("/" if folder else "")):
                out.append(p)
        return out

    def elsewhere(self, unit: str, pattern: str) -> list[str]:
        """Files (or folders) that have the name or match the wildcard of `pattern` but sit elsewhere in the unit, e.g. includes/libft.h
        for libft.h. Outside the strict projects the whole repository is searched (the layout is free there)."""
        ctx = self.ctx
        folder = pattern.endswith("/")
        name = pattern.rstrip("/").rsplit("/", 1)[-1]
        if not name or name in ("*", "**"):
            return []
        root = ctx.repo.resolve()
        hits: list[str] = []
        for p in (ctx.unit_dir(unit) if ctx.strict_layout else root).rglob(name):
            if (p.is_dir() if folder else p.is_file()) and not p.is_symlink() and p.is_relative_to(root):
                rel = p.relative_to(root).as_posix()
                if ".git" not in rel.split("/") and not ctx.is_vendored(rel + ("/" if folder else "")):
                    hits.append(rel + ("/" if folder else ""))
            if len(hits) >= 3:
                break
        return hits


@dataclass
class Search:
    missing: list[str] = field(default_factory=list)
    relocated: list[str] = field(default_factory=list)       # there, but not where the list says
    expected: list[str] = field(default_factory=list)        # only shown in an example layout of the subject
    found: int = 0


class RuleSearch:
    """One look for every file pattern of a `required_files` rule."""

    def __init__(self, ctx: Ctx, rule: Rule) -> None:
        self.ctx, self.rule, self.finder = ctx, rule, FileFinder(ctx)
        # `root`: the subject says these belong at the root of the repository (binding only in the strict projects).
        # `soft`: they only appear in an example layout.
        self.root = set(rule.params.get("root") or []) if ctx.strict_layout else set()
        self.soft = set(rule.params.get("soft") or [])

    def run(self) -> Search:
        search = Search()
        for alternatives in self.rule.params["files"]:
            if any(self.finder.find(self.rule.unit, alt, root_only=alt in self.root) for alt in alternatives):
                search.found += 1
            else:
                self._absent(search, alternatives)
        return search

    def _absent(self, search: Search, alternatives: list[str]) -> None:
        wanted = " or ".join(alternatives)
        elsewhere = [hit for alt in alternatives for hit in self.finder.elsewhere(self.rule.unit, alt)][:3]
        if elsewhere and all(alt in self.root for alt in alternatives):     # the subject is explicit about the root: elsewhere is not enough
            search.missing.append(f"{wanted} (it is at {', '.join(f'`{hit}`' for hit in elsewhere)}, but the subject says it belongs at the root)")
        elif elsewhere:                             # there, but not where the list says: a question about structure, not a missing file
            search.relocated.append(f"{wanted} → {', '.join(f'`{hit}`' for hit in elsewhere)}")
        elif all(alt in self.soft for alt in alternatives):   # only shown in an example layout of the subject
            search.expected.append(wanted)
        else:
            lowered = {p.name.lower() for p in self.ctx.unit_dir(self.rule.unit).iterdir()}
            hint = " (a file exists with different letter case)" if any(alt.lower() in lowered for alt in alternatives if "*" not in alt) else ""
            search.missing.append(wanted + hint)


def after_make(ctx: Ctx, unit: str) -> BuildResult | None:
    """Build the unit, for files that are only there once `make` has run (a Makefile that downloads them, a submodule).
    None when nothing can be built here."""
    if ctx.sandbox is None or not ctx.has_makefile(unit):
        return None
    try:
        return ctx.build(unit)
    except SandboxError:
        return None
