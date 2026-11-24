"""The programs the runtime checks run."""

from __future__ import annotations

from pathlib import Path

from verdict.checks.context.ctx import Ctx


def runnable_targets(ctx: Ctx) -> list[tuple[str, Path]]:
    """(unit, program) of every built unit: the programs the subject names, else whatever executable the build left."""
    out: list[tuple[str, Path]] = []
    for unit in ctx.units():
        if not ctx.has_makefile(unit) or not ctx.build(unit).ok:
            continue
        wanted = [ctx.unit_dir(unit) / n for n in ctx.programs(unit, "mandatory") if not n.endswith(".a")]
        exes = [p for p in wanted if p.is_file()] or [p for p in ctx.executables(unit)]
        out += [(unit, p) for p in exes]
    return out
