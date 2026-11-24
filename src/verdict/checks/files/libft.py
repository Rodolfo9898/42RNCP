"""`copy the sources of your libft and its Makefile into a libft folder`."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker
from verdict.checks.files.finder import after_make
from verdict.core.models import CheckResult, Evidence, Rule

INCLUDE_LIBFT = re.compile(r'#\s*include\s*[<"](?:[\w./]*/)?libft\.h[>"]')
MADE_NOTE = " It is only there once `make` has run (downloaded by the Makefile), which counts."


def libft_copies(ctx: Ctx) -> list[str]:
    """Folders that hold a copy of a libft: libft.h with a Makefile in the same folder or above it, inside the project. Any folder name
    counts outside the strict projects; how it got there does not matter (committed, a submodule, downloaded by the Makefile)."""
    root = ctx.repo.resolve()
    out: list[str] = []
    for header in root.rglob("libft.h"):
        rel = header.relative_to(root)
        if ".git" in rel.parts or ctx.is_vendored(rel) or len(rel.parts) == 1:
            continue
        for folder in [header.parent, *header.parent.parents]:
            if folder == root:
                break
            if (folder / "Makefile").is_file():
                out.append(folder.relative_to(root).as_posix())
                break
    return sorted(set(out))


def uses_libft(ctx: Ctx) -> list[str]:
    """Where the project says it uses a libft: a Makefile that names it, or a source that includes libft.h."""
    found: list[str] = []
    for rel in ctx.files():
        if ctx.is_vendored(rel):
            continue
        if rel.name == "Makefile" and re.search(r"\blibft\b", ctx.read(rel), re.I):
            found.append(rel.as_posix())
        elif rel.suffix in (".c", ".h") and INCLUDE_LIBFT.search(ctx.read(rel)):
            found.append(rel.as_posix())
        if len(found) >= 3:
            break
    return found


@dataclass
class LibftUse:
    users: list[str]        # the files that say the project uses a libft
    copies: list[str]       # the folders that hold one


class LibftCopyChecker(Checker):
    """A project that uses a libft has its sources and Makefile in the repository (committed, a submodule, or downloaded by `make`)."""

    kind = "libft_copy"

    def skip(self, ctx: Ctx, rule: Rule) -> CheckResult | None:
        if any(r.kind == "program" and r.params.get("program") == "libft.a" for r in ctx.rules):
            return self.result(rule, "na", "This project is the libft itself.")
        return None

    def prepare(self, ctx: Ctx, rule: Rule) -> LibftUse:
        return LibftUse(uses_libft(ctx), libft_copies(ctx))

    def evaluate(self, ctx: Ctx, rule: Rule, use: LibftUse) -> Iterable[CheckResult]:
        if not use.users and not use.copies:
            yield self.result(rule, "na", "The project does not use a libft.")
            return
        copies, made = use.copies, ""
        if not copies:
            build = after_make(ctx, ".")
            if build is not None:
                copies = libft_copies(ctx)
                made = MADE_NOTE if copies else ""
                if not copies and (reason := ctx.offline_reason(build)):
                    yield self.result(rule, "warn", f"The project uses a libft ({', '.join(use.users)}) that is not in the repository yet. {reason}",
                                      log=build.log)
                    return
        yield self._found(ctx, rule, copies, made) if copies else self._missing(rule, use.users)

    def _found(self, ctx: Ctx, rule: Rule, copies: list[str], made: str) -> CheckResult:
        modules = ctx.submodule_paths()

        def how(folder: str) -> str:
            return f"`{folder}/` (a git submodule)" if any(folder == m or folder.startswith(m.rstrip("/") + "/") for m in modules) else f"`{folder}/`"

        found = f"The libft sources and Makefile are in the repository: {', '.join(how(c) for c in copies[:3])}.{made}"
        evidence = [Evidence(file=f"{c}/Makefile") for c in copies[:3]]
        if any(Path(c).name == "libft" for c in copies):
            return self.result(rule, "pass", found, evidence=evidence)
        if ctx.strict_layout:                         # ft_printf: the format is binding, and the subject says "a libft folder"
            return self.result(rule, "warn", f"{found} The subject asks for a folder called libft, and in this project the format is binding.",
                               evidence=evidence)
        return self.result(rule, "pass", f"{found} The folder is not called libft, which is fine: the layout is free outside libft, "
                                         "ft_printf and get_next_line.", evidence=evidence)

    def _missing(self, rule: Rule, users: list[str]) -> CheckResult:
        return self.result(rule, "fail", f"The project uses a libft ({', '.join(users)}), but its sources and Makefile are not in the repository "
                                         "(committed, as a submodule, or downloaded by `make`).",
                           evidence=[Evidence(file=u) for u in users])
