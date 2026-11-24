"""Suggestions about how the project is laid out: README, .gitignore, where the sources sit, leftovers, the Makefile."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from verdict.checks import Ctx
from verdict.core.models import Improvement
from verdict.reports.improve.heuristic import Heuristic, evidence
from verdict.reports.improve.readme import readme_required, readme_status

SHORT_README = 12
ALL_AT_THE_ROOT = 8
LEFTOVER_SUFFIX = re.compile(r"(~|\.bak|\.orig|\.swp|\.tmp)$")
LEFTOVER_NAME = re.compile(r"(test|tmp|old|copy)\w*\.(c|cpp|h)", re.I)


class StructureHeuristic(Heuristic):
    def improvements(self, ctx: Ctx) -> Iterable[Improvement]:
        yield from self._readme(ctx)
        files = ctx.files()
        yield from self._layout(ctx, files)
        yield from self._leftovers(files)
        for makefile in (p for p in files if p.name == "Makefile" and not any("mlx" in part.lower() for part in p.parts)):
            yield from self._makefile(ctx, makefile)

    @staticmethod
    def _readme(ctx: Ctx) -> Iterable[Improvement]:
        status = readme_status(ctx)
        required = readme_required(ctx)
        if not status["present"]:
            if required:
                yield Improvement(
                    category="structure", priority="high", title="No README found",
                    detail="The subject requires a README.md at the root: the first line in italics (*This project has been created "
                           "as part of the 42 curriculum by <login>*), then Description, Instructions (how to build and run) and "
                           "Resources (references, and how AI was used).")
            else:
                yield Improvement(
                    category="structure", priority="medium", title="No README found",
                    detail="None of the loaded subjects requires one, but a README is the best guide to a project: what it does, how to "
                           "build and run it, how the code is organised and why the main design choices were made. Anyone reading "
                           "the repository (a reviewer, or you in six months) will start there.")
        elif status["name"] != "README.md":
            yield Improvement(category="structure", priority="medium" if required else "low", title=f"Rename {status['name']} to README.md",
                              detail="A file named exactly README.md is shown automatically by Git hosting sites"
                                     + (" and the subject requires that name." if required else "."))
        elif status["lines"] < SHORT_README:
            yield Improvement(category="structure", priority="low", title="README is very short",
                              detail=f"Only {status['lines']} non-empty lines. Treat it as a guide to the project: explain the goal, how "
                                     "to compile and run it, how the code is organised, and give a usage example.",
                              evidence=[evidence("README.md", 1)])

    @staticmethod
    def _layout(ctx: Ctx, files: list[Path]) -> Iterable[Improvement]:
        sources = [p for p in ctx.source_files() if len(p.parts) == 1]
        if not any(p.name == ".gitignore" for p in files if len(p.parts) == 1):
            yield Improvement(category="structure", priority="medium", title="No .gitignore",
                              detail="Add one so object files, binaries and editor files are never committed.")
        if len(sources) > ALL_AT_THE_ROOT and not any(p.parts[0] in ("src", "srcs", "sources") for p in files if len(p.parts) > 1):
            yield Improvement(category="structure", priority="low", title="All sources are at the repository root",
                              detail=f"{len(sources)} source/header files sit next to the Makefile. Group them (for example "
                                     "src/ for .c files and include/ for headers) unless the subject says to keep them at the root.")

    @staticmethod
    def _leftovers(files: list[Path]) -> Iterable[Improvement]:
        leftovers = [p for p in files if LEFTOVER_SUFFIX.search(p.name)
                     or p.name in ("a.out", "core", "nohup.out") or LEFTOVER_NAME.fullmatch(p.name)]
        if leftovers:
            yield Improvement(category="structure", priority="low", title="Leftover or scratch files",
                              detail="These look like experiments or backups; remove them or move them out of the repository.",
                              evidence=[evidence(p) for p in leftovers[:10]])

    @staticmethod
    def _makefile(ctx: Ctx, makefile: Path) -> Iterable[Improvement]:
        text = ctx.read(makefile)
        wild = [(i + 1, l) for i, l in enumerate(text.splitlines()) if re.search(r"\$\(wildcard|\bSRCS?\s*[:+]?=.*\*\.c", l)]
        if wild:
            yield Improvement(category="structure", priority="medium", title="Makefile finds sources with a wildcard",
                              detail="42 projects must list source files explicitly so that adding a file never silently changes the build.",
                              evidence=[evidence(makefile, n, l.strip()) for n, l in wild[:5]])
        if ".PHONY" not in text:
            yield Improvement(category="structure", priority="low", title="Makefile has no .PHONY line",
                              detail="Declare all, clean, fclean and re as .PHONY so a file with the same name never blocks them.",
                              evidence=[evidence(makefile)])
