"""The symbols of the build, read with `nm`."""

from __future__ import annotations

from verdict.checks.context.ctx import Ctx


def imported_symbols(ctx: Ctx, unit: str, targets: list[str]) -> tuple[set[str], set[str]]:
    """(what the targets use but do not define themselves, what they define): the global symbols of `nm -g`."""
    undefined: set[str] = set()
    defined: set[str] = set()
    for target in targets:
        res = ctx.run(["nm", "-g", target], unit, timeout=60)
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            kind, name = parts[-2], parts[-1].split("@", 1)[0]
            if kind == "U":
                undefined.add(name)
            elif kind != "w" and len(kind) == 1:
                defined.add(name)
    return undefined - defined, defined


def library_functions(ctx: Ctx, unit: str, library: str) -> set[str]:
    """The names a library defines (macOS prefixes symbols with an underscore: `_ft_x` is `ft_x`)."""
    symbols = ctx.run(["nm", "-g", "--defined-only", library], unit, timeout=60).stdout.split()
    return {sym[1:] if sym.startswith("_ft_") else sym for sym in symbols}
