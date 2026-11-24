"""What `make clean`, `make fclean` and `make re` do to the build."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Audit
from verdict.checks.engine.results import result
from verdict.core.models import CheckResult, Evidence


class MakefileBehavior(Audit):
    """Runs the cleaning and rebuilding rules of every built unit, last, because they undo the build (an audit, outside the
    rules of the subject)."""

    needs_sandbox = True

    def run(self, ctx: Ctx) -> Iterable[CheckResult]:
        for unit in ctx.units():
            if not ctx.has_makefile(unit) or not ctx.build(unit).ok:
                continue
            yield from UnitBehavior(ctx, unit).results()


class UnitBehavior:
    """The three cleaning rules of one built unit, judged one after the other on the same folder."""

    def __init__(self, ctx: Ctx, unit: str) -> None:
        self.ctx, self.unit = ctx, unit
        self.prefix = "" if unit == "." else f"{unit}: "
        self.names = ctx.programs(unit, "mandatory") or [p.name for p in ctx.executables(unit) + ctx.libraries(unit)]
        self.base = ctx.unit_dir(unit)

    def results(self) -> Iterator[CheckResult]:
        yield self._clean()
        yield self._fclean()
        yield self._rebuild()

    def _objects(self) -> list[str]:
        return [p.as_posix() for p in self.ctx.walk(self.base)
                if p.suffix == ".o" and not self.ctx.is_vendored((self.base / p).relative_to(self.ctx.repo.resolve()))]

    def _present(self) -> list[str]:
        return [n for n in self.names if (self.base / n).is_file()]

    def _lost(self) -> str:
        return ", ".join(set(self.names) - set(self._present()))

    def _clean(self) -> CheckResult:
        clean = self.ctx.run(["make", "clean"], self.unit, timeout=120)
        left = self._objects()
        if not clean.ok:
            return result(None, "fail", "`make clean` failed.", title=f"{self.prefix}`make clean` works", log=clean.output)
        if left:
            return result(None, "fail", f"`make clean` left {len(left)} object file(s).", title=f"{self.prefix}`make clean` removes objects",
                          evidence=[Evidence(file=f) for f in left[:10]])
        if self.names and len(self._present()) != len(self.names):
            return result(None, "fail", f"`make clean` also removed the program(s): {self._lost()}. It should only remove objects.",
                          title=f"{self.prefix}`make clean` keeps the program")
        return result(None, "pass", "Objects removed, program kept.", title=f"{self.prefix}`make clean` removes objects and keeps the program")

    def _fclean(self) -> CheckResult:
        fclean = self.ctx.run(["make", "fclean"], self.unit, timeout=120)
        left = self._objects() + self._present()
        if not fclean.ok:
            return result(None, "fail", "`make fclean` failed.", title=f"{self.prefix}`make fclean` works", log=fclean.output)
        if left:
            return result(None, "fail", f"`make fclean` left: {', '.join(left[:6])}.", title=f"{self.prefix}`make fclean` removes everything built")
        return result(None, "pass", "Objects and program removed.", title=f"{self.prefix}`make fclean` removes everything built")

    def _rebuild(self) -> CheckResult:
        rebuilt = self.ctx.run(["make", "re"], self.unit, timeout=240)
        if not rebuilt.ok:
            return result(None, "fail", "`make re` failed.", title=f"{self.prefix}`make re` rebuilds", log=rebuilt.output)
        if self.names and len(self._present()) != len(self.names):
            return result(None, "fail", f"`make re` did not produce: {self._lost()}.", title=f"{self.prefix}`make re` rebuilds")
        return result(None, "pass", "Rebuilt from scratch.", title=f"{self.prefix}`make re` rebuilds")
