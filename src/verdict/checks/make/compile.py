"""How the project is compiled: with which flags, and that it still is under C++98."""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Checker, Phase
from verdict.checks.engine.results import tail
from verdict.core.models import CheckResult, Evidence, Rule

COMPILER_LINE = re.compile(r"^\s*@?\s*(\S*(?:clang\+\+|g\+\+|c\+\+|gcc|clang|cc))\s")
SOURCE_ARG = re.compile(r"\S+\.(?:c|cpp|cc)\b")


@dataclass
class CompileScan:
    seen: int = 0
    bad: list[Evidence] = field(default_factory=list)
    odd_compilers: set[str] = field(default_factory=set)      # gcc or clang where the subject asks for cc (g++ for c++)


class FlagsChecker(Checker):
    """Every compile command of the Makefile carries the flags the subject lists, and calls the compiler it names."""

    kind = "flags"
    phase = Phase.BUILD

    def prepare(self, ctx: Ctx, rule: Rule) -> CompileScan:
        wanted: list[str] = rule.params["flags"]
        compiler = rule.params.get("compiler", "cc")
        scan = CompileScan()
        for unit in ctx.units():
            if not ctx.has_makefile(unit):
                continue
            res = ctx.run(["make", "-n", "-B"], unit, timeout=60)  # -B: list every command, even for up-to-date targets
            for line in self._compile_lines(res.stdout):
                self._read(scan, unit, line, wanted, compiler)
        return scan

    @staticmethod
    def _compile_lines(output: str) -> list[str]:
        return [l for l in output.splitlines() if COMPILER_LINE.match(l) and SOURCE_ARG.search(l)]

    @staticmethod
    def _read(scan: CompileScan, unit: str, line: str, wanted: list[str], compiler: str) -> None:
        scan.seen += 1
        tokens = shlex.split(line.replace("@", " ", 1), posix=True) if "'" not in line else line.split()
        missing = [f for f in wanted if f not in tokens]
        if missing:
            scan.bad.append(Evidence(file=f"{unit}/Makefile".lstrip("./"), snippet=f"missing {' '.join(missing)}: {line.strip()[:160]}"))
        exe = Path(tokens[0]).name if tokens else ""
        if compiler == "cc" and exe in ("gcc", "clang") or compiler == "c++" and exe in ("g++", "clang++"):
            scan.odd_compilers.add(exe)

    def evaluate(self, ctx: Ctx, rule: Rule, scan: CompileScan) -> Iterable[CheckResult]:
        wanted: list[str] = rule.params["flags"]
        compiler = rule.params.get("compiler", "cc")
        if scan.seen == 0:
            yield self.result(rule, "warn", "No compile commands were visible in `make -n -B`; could not verify the flags.")
        elif scan.bad:
            yield self.result(rule, "fail", f"{len(scan.bad)} of {scan.seen} compile command(s) lack {' '.join(wanted)}.", evidence=scan.bad[:20])
        elif scan.odd_compilers:
            yield self.result(rule, "warn", f"Flags are present, but the subject asks for `{compiler}` and the Makefile calls {', '.join(sorted(scan.odd_compilers))}.")
        else:
            yield self.result(rule, "pass", f"All {scan.seen} compile command(s) use {' '.join(wanted)}.")


class Std98Checker(Checker):
    """The C++ sources still compile under -std=c++98 with the strict flags."""

    kind = "std98"
    phase = Phase.BUILD

    def prepare(self, ctx: Ctx, rule: Rule) -> tuple[int, list[str]]:
        failures: list[str] = []
        checked = 0
        for unit in ctx.units():
            files = [p for p in ctx.source_files(unit) if p.suffix == ".cpp"]
            if not files:
                continue
            checked += 1
            base = ctx.unit_dir(unit)
            rels = [str((ctx.repo / p).resolve().relative_to(base)) for p in files]
            res = ctx.run(["c++", "-Wall", "-Wextra", "-Werror", "-std=c++98", "-fsyntax-only", "-I.", *rels], unit, timeout=120)
            if not res.ok:
                failures.append(f"{unit}:\n{tail(res.output, 12)}")
        return checked, failures

    def evaluate(self, ctx: Ctx, rule: Rule, facts: tuple[int, list[str]]) -> Iterable[CheckResult]:
        checked, failures = facts
        if checked == 0:
            yield self.result(rule, "skipped", "No .cpp files to compile.")
        elif failures:
            yield self.result(rule, "fail", "Does not compile with -std=c++98.", log="\n\n".join(failures))
        else:
            yield self.result(rule, "pass", f"All {checked} unit(s) compile with -std=c++98 and -Wall -Wextra -Werror.")
