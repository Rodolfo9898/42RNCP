"""Checks that build and run the repository inside the sandbox."""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable
from pathlib import Path

from ..models import CheckResult, Evidence, Rule
from ..spec import MATH_FUNCTIONS
from . import (
    EXCLUDED_DIRS, PHASE_ANALYSIS, PHASE_BUILD, PHASE_RUNTIME, Ctx, checker, grep, label, result,
)

COMPILER_LINE = re.compile(r"^\s*@?\s*(\S*(?:clang\+\+|g\+\+|c\+\+|gcc|clang|cc))\s")
SOURCE_ARG = re.compile(r"\S+\.(?:c|cpp|cc)\b")
ARCHIVE_OR_LINK_LINE = re.compile(r"^\s*@?\s*(?:\S*/)?(?:cc|gcc|clang|c\+\+|g\+\+|clang\+\+|ar|ranlib|ld)\b")
SMOKE_ARGS = [[], ["abc"], ["1", "2", "3"], ["-1"]]
LEAK_ARGS = [[], ["abc"], ["3", "2", "1"]]
COMPILER_EMITTED = {"memcpy", "memset", "memmove", "memcmp"}


def _tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


# --------------------------------------------------------------------------- build


@checker("program", PHASE_BUILD)
def program(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    name = rule.params["program"]
    title = label(rule, f"`make{' bonus' if rule.params.get('bonus_target') else ''}` builds `{name}`")
    build = ctx.build(rule.unit, bool(rule.params.get("bonus_target")))
    if not build.ok:
        yield result(rule, "fail", "The build failed." if build.ran else build.log, title=title, log=build.log)
        return
    path = ctx.unit_dir(rule.unit) / name
    if not path.is_file():
        yield result(rule, "fail", f"The build succeeded but `{name}` was not produced.", title=title, log=build.log)
    elif path.stat().st_size == 0:
        yield result(rule, "fail", f"`{name}` is empty.", title=title, log=build.log)
    else:
        yield result(rule, "pass", f"`{name}` was built.", title=title, log=build.log)


@checker("build_unit", PHASE_BUILD)
def build_unit(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    build = ctx.build(rule.unit)
    if not build.ok:
        yield result(rule, "fail", "The build failed." if build.ran else build.log, log=build.log)
        return
    built = ctx.executables(rule.unit) + ctx.libraries(rule.unit)
    if built:
        yield result(rule, "pass", f"Built {', '.join(p.name for p in built)}.", log=build.log)
    else:
        yield result(rule, "warn", "The build succeeded but produced no executable.", log=build.log)


def _compile_lines(output: str) -> list[str]:
    return [l for l in output.splitlines() if COMPILER_LINE.match(l) and SOURCE_ARG.search(l)]


@checker("flags", PHASE_BUILD)
def flags(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    wanted: list[str] = rule.params["flags"]
    compiler = rule.params.get("compiler", "cc")
    bad: list[Evidence] = []
    seen = 0
    odd_compilers: set[str] = set()
    for unit in ctx.units():
        if not ctx.has_makefile(unit):
            continue
        res = ctx.run(["make", "-n", "-B"], unit, timeout=60)  # -B: list every command, even for up-to-date targets
        for line in _compile_lines(res.stdout):
            seen += 1
            tokens = shlex.split(line.replace("@", " ", 1), posix=True) if "'" not in line else line.split()
            missing = [f for f in wanted if f not in tokens]
            if missing:
                bad.append(Evidence(file=f"{unit}/Makefile".lstrip("./"), snippet=f"missing {' '.join(missing)}: {line.strip()[:160]}"))
            exe = Path(tokens[0]).name if tokens else ""
            if compiler == "cc" and exe in ("gcc", "clang") or compiler == "c++" and exe in ("g++", "clang++"):
                odd_compilers.add(exe)
    if seen == 0:
        yield result(rule, "warn", "No compile commands were visible in `make -n -B`; could not verify the flags.")
    elif bad:
        yield result(rule, "fail", f"{len(bad)} of {seen} compile command(s) lack {' '.join(wanted)}.", evidence=bad[:20])
    elif odd_compilers:
        yield result(rule, "warn", f"Flags are present, but the subject asks for `{compiler}` and the Makefile calls {', '.join(sorted(odd_compilers))}.")
    else:
        yield result(rule, "pass", f"All {seen} compile command(s) use {' '.join(wanted)}.")


@checker("std98", PHASE_BUILD)
def std98(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
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
            failures.append(f"{unit}:\n{_tail(res.output, 12)}")
    if checked == 0:
        yield result(rule, "skipped", "No .cpp files to compile.")
    elif failures:
        yield result(rule, "fail", "Does not compile with -std=c++98.", log="\n\n".join(failures))
    else:
        yield result(rule, "pass", f"All {checked} unit(s) compile with -std=c++98 and -Wall -Wextra -Werror.")


# --------------------------------------------------------------------------- analysis


@checker("no_relink", PHASE_ANALYSIS)
def no_relink(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    offenders: list[Evidence] = []
    checked = 0
    for unit in ctx.units():
        if not ctx.has_makefile(unit) or not ctx.build(unit).ok:
            continue
        checked += 1
        res = ctx.run(["make", "-n"], unit, timeout=60)
        for line in res.stdout.splitlines():
            if ARCHIVE_OR_LINK_LINE.match(line):
                offenders.append(Evidence(file=f"{unit}/Makefile".lstrip("./"), snippet=line.strip()[:200]))
    if checked == 0:
        yield result(rule, "skipped", "Nothing was built, so relinking could not be tested.")
    elif offenders:
        yield result(rule, "fail", "A second `make` would rebuild/relink although nothing changed.", evidence=offenders[:10])
    else:
        yield result(rule, "pass", "A second `make` has nothing to do.")


def _symbols(ctx: Ctx, unit: str, targets: list[str]) -> tuple[set[str], set[str]]:
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


@checker("allowed_functions", PHASE_ANALYSIS)
def allowed_functions(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    if ctx.lang == "cpp":
        yield result(rule, "manual", rule.text, auto=False)
        return
    unit = rule.unit
    names = [n for n in ctx.programs(unit, rule.section)]
    targets = [n for n in names if (ctx.unit_dir(unit) / n).is_file()]
    note = ""
    if not targets:
        # No program name in the subject (e.g. get_next_line): compile each source to an object.
        objs: list[str] = []
        for i, rel in enumerate(p for p in ctx.source_files(unit) if p.suffix == ".c"):
            out = f"/tmp/verdict_{abs(hash(str(ctx.repo)))}_{i}.o"
            res = ctx.run(["cc", "-c", "-D", "BUFFER_SIZE=42", "-I.", "-o", out, str((ctx.repo / rel).resolve().relative_to(ctx.unit_dir(unit)))], unit, timeout=60)
            if res.ok:
                objs.append(out)
        targets = objs
        note = " (compiled from sources)"
    if not targets:
        yield result(rule, "skipped", "Nothing was built, so external calls could not be inspected.")
        return

    undefined, _defined = _symbols(ctx, unit, targets)
    allowed = set(rule.params["functions"])
    if rule.params.get("libft"):
        allowed |= {"malloc", "free", "write"}
    undefined = {u for u in undefined if not u.startswith("_")}
    if rule.params.get("math"):
        allowed |= set(MATH_FUNCTIONS) | {f + "f" for f in MATH_FUNCTIONS} | {f + "l" for f in MATH_FUNCTIONS}
    forbidden = {u for u in undefined - allowed if not (rule.params.get("mlx") and re.match(r"(mlx_|X[A-Z]|shm)", u))}

    violations: list[Evidence] = []
    sources = ctx.source_files(unit)
    for name in sorted(forbidden):
        violations += grep(ctx, sources, re.compile(rf"(?<![\w.>])\b{re.escape(name)}\s*\("), limit=5)
    if violations:
        yield result(rule, "fail", f"Calls to functions that are not authorized: {', '.join(sorted(forbidden))}.{note}", evidence=violations[:25])
    elif forbidden and forbidden <= COMPILER_EMITTED:
        yield result(rule, "pass", f"Only compiler-generated calls to {', '.join(sorted(forbidden))}.{note}")
    else:
        extra = f" ({len(forbidden)} imported symbol(s) come from linked libraries, not from the repo's own calls.)" if forbidden else ""
        yield result(rule, "pass", f"No unauthorized function calls found{note}.{extra}")


_DEF_RE = r"^(?!static\b)[A-Za-z_][\w \t\*]*[ \t\*]{name}\s*\("


@checker("functions_defined", PHASE_ANALYSIS)
def functions_defined(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    sources = [p for p in ctx.source_files(rule.unit) if p.suffix == ".c"]
    text = "\n".join(ctx.read(p) for p in sources)
    names = rule.params["names"]
    missing = [n for n in names if not re.search(_DEF_RE.format(name=re.escape(n)), text, re.M)]
    if missing:
        yield result(rule, "fail", f"{len(missing)} of {len(names)} required function(s) not found in the sources: {', '.join(missing)}.")
        return
    # Defined in the sources is not enough: they must be in the library that `make` actually builds.
    library = next((n for n in ctx.programs(rule.unit, rule.section) if n.endswith(".a")), None)
    if library and ctx.sandbox is not None and ctx.build(rule.unit).ok and (ctx.unit_dir(rule.unit) / library).is_file():
        symbols = ctx.run(["nm", "-g", "--defined-only", library], rule.unit, timeout=60).stdout.split()
        built = {sym[1:] if sym.startswith("_ft_") else sym for sym in symbols}      # (macOS prefixes symbols with _)
        absent = [n for n in names if n not in built]
        if absent:
            yield result(rule, "fail",
                         f"{len(absent)} of {len(names)} required function(s) are in the sources but NOT in the {library} that `make` builds: "
                         f"{', '.join(absent)}. Check which Makefile rule adds them: the subject requires them in the library.",
                         title=label(rule, f"Required functions are in {library}"))
            return
        yield result(rule, "pass", f"All {len(names)} required function(s) are defined in the sources and present in {library}.",
                     title=label(rule, f"Required functions are in {library}"))
        return
    yield result(rule, "pass", f"All {len(names)} required function(s) are defined in the sources.")


def _norm_report(ctx: Ctx) -> dict | None:
    if "norm" in ctx.cache:
        return ctx.cache["norm"]
    files = [p.as_posix() for p in ctx.source_files(".") if p.suffix in (".c", ".h")]
    report: dict = {"files": len(files), "errors": {}, "available": True}
    if not files:
        ctx.cache["norm"] = report
        return report
    for start in range(0, len(files), 100):
        res = ctx.run(["norminette", *files[start:start + 100]], ".", timeout=180)
        if res.rc == 127:
            report["available"] = False
            break
        current = None
        for line in res.stdout.splitlines():
            line = re.sub(r"\x1b\[[0-9;]*m", "", line)
            m = re.match(r"^(\S+): (OK!|Error!)$", line)
            if m:
                current = m.group(1)
                continue
            m = re.match(r"^(Error|Notice): (\w+)\s+\(line:\s*(\d+), col:\s*(\d+)\):\s*(.*)$", line)
            if m and current:
                report["errors"].setdefault(current, []).append((m.group(2), int(m.group(3)), m.group(5), m.group(1)))
    ctx.cache["norm"] = report
    return report


@checker("norm", PHASE_ANALYSIS)
def norm(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    if ctx.lang == "cpp":
        yield result(rule, "skipped", "The Norm does not apply to C++ projects.")
        return
    report = _norm_report(ctx)
    if not report["available"]:
        yield result(rule, "skipped", "norminette is not installed in the sandbox.")
    elif report["files"] == 0:
        yield result(rule, "fail", "No .c/.h files to check.")
    else:
        errors = {f: [e for e in errs if e[3] == "Error"] for f, errs in report["errors"].items()}
        errors = {f: errs for f, errs in errors.items() if errs}
        if errors:
            evidence = [Evidence(file=f, line=line, snippet=f"{code}: {msg}")
                        for f, errs in errors.items() for code, line, msg, _ in errs][:60]
            total = sum(len(v) for v in errors.values())
            yield result(rule, "fail", f"{total} Norm error(s) in {len(errors)} of {report['files']} file(s).", evidence=evidence)
        else:
            yield result(rule, "pass", f"norminette: all {report['files']} file(s) OK.")


@checker("no_globals", PHASE_ANALYSIS)
def no_globals(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    if ctx.lang == "cpp":
        yield result(rule, "skipped", "Not checked for C++ projects.")
        return
    report = _norm_report(ctx)
    if not report["available"]:
        yield result(rule, "manual", rule.text, auto=False)
        return
    hits = [Evidence(file=f, line=line, snippet=msg) for f, errs in report["errors"].items()
            for code, line, msg, _ in errs if code == "GLOBAL_VAR_DETECTED"]
    if hits:
        yield result(rule, "fail", f"{len(hits)} global variable(s) detected by norminette.", evidence=hits[:30])
    else:
        yield result(rule, "pass", "norminette detected no global variables (the subject may allow some; see the manual items).")


# --------------------------------------------------------------------------- runtime


def _targets(ctx: Ctx) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for unit in ctx.units():
        if not ctx.has_makefile(unit) or not ctx.build(unit).ok:
            continue
        wanted = [ctx.unit_dir(unit) / n for n in ctx.programs(unit, "mandatory") if not n.endswith(".a")]
        exes = [p for p in wanted if p.is_file()] or [p for p in ctx.executables(unit)]
        out += [(unit, p) for p in exes]
    return out


@checker("no_crash", PHASE_RUNTIME)
def no_crash(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    targets = _targets(ctx)
    if not targets:
        yield result(rule, "skipped", "No executable was built (libraries need a test program; see the manual items).")
        return
    crashes: list[str] = []
    runs = 0
    for unit, exe in targets:
        for args in SMOKE_ARGS:
            runs += 1
            res = ctx.run([f"./{exe.name}", *args], unit, timeout=5)
            if res.crashed:
                crashes.append(f"$ ./{exe.name} {' '.join(args)}\n  killed by signal {-res.rc}\n{_tail(res.output, 5)}")
    if crashes:
        yield result(rule, "fail", f"{len(crashes)} of {runs} basic run(s) crashed.", log="\n\n".join(crashes))
    else:
        yield result(rule, "pass", f"{runs} basic run(s) (no arguments, invalid arguments, a few numbers) did not crash. "
                     "This is a smoke test, not a full evaluation.")


@checker("no_leaks", PHASE_RUNTIME)
def no_leaks(ctx: Ctx, rule: Rule) -> Iterable[CheckResult]:
    targets = _targets(ctx)
    if not targets:
        yield result(rule, "skipped", "No executable was built (libraries need a test program).")
        return
    leaks: list[str] = []
    runs = 0
    for unit, exe in targets:
        for args in LEAK_ARGS:
            res = ctx.run(["valgrind", "--leak-check=full", "--errors-for-leak-kinds=definite",
                           "--error-exitcode=42", "-q", f"./{exe.name}", *args], unit, timeout=60)
            if res.rc == 127:
                yield result(rule, "skipped", "valgrind is not installed in the sandbox.")
                return
            if res.timed_out:
                continue
            runs += 1
            if res.rc == 42:
                leaks.append(f"$ valgrind ./{exe.name} {' '.join(args)}\n{_tail(res.stderr, 20)}")
    if leaks:
        yield result(rule, "fail", f"valgrind reports leaks/errors in {len(leaks)} of {runs} run(s).", log="\n\n".join(leaks))
    elif runs == 0:
        yield result(rule, "skipped", "Every run timed out under valgrind.")
    else:
        yield result(rule, "pass", f"valgrind found no definite leaks in {runs} basic run(s). Leaks on other inputs are not covered.")


# --------------------------------------------------------------------------- final


def makefile_behavior(ctx: Ctx) -> Iterable[CheckResult]:
    for unit in ctx.units():
        if not ctx.has_makefile(unit) or not ctx.build(unit).ok:
            continue
        prefix = "" if unit == "." else f"{unit}: "
        names = ctx.programs(unit, "mandatory") or [p.name for p in ctx.executables(unit) + ctx.libraries(unit)]
        base = ctx.unit_dir(unit)

        def objects() -> list[str]:
            return [p.as_posix() for p in ctx.walk(base) if p.suffix == ".o" and not EXCLUDED_DIRS.search("/" + p.as_posix())]

        def present() -> list[str]:
            return [n for n in names if (base / n).is_file()]

        clean = ctx.run(["make", "clean"], unit, timeout=120)
        left = objects()
        if not clean.ok:
            yield result(None, "fail", "`make clean` failed.", title=f"{prefix}`make clean` works", log=clean.output)
        elif left:
            yield result(None, "fail", f"`make clean` left {len(left)} object file(s).", title=f"{prefix}`make clean` removes objects",
                         evidence=[Evidence(file=f) for f in left[:10]])
        elif names and len(present()) != len(names):
            yield result(None, "fail", f"`make clean` also removed the program(s): {', '.join(set(names) - set(present()))}. It should only remove objects.",
                         title=f"{prefix}`make clean` keeps the program")
        else:
            yield result(None, "pass", "Objects removed, program kept.", title=f"{prefix}`make clean` removes objects and keeps the program")

        fclean = ctx.run(["make", "fclean"], unit, timeout=120)
        left = objects() + present()
        if not fclean.ok:
            yield result(None, "fail", "`make fclean` failed.", title=f"{prefix}`make fclean` works", log=fclean.output)
        elif left:
            yield result(None, "fail", f"`make fclean` left: {', '.join(left[:6])}.", title=f"{prefix}`make fclean` removes everything built")
        else:
            yield result(None, "pass", "Objects and program removed.", title=f"{prefix}`make fclean` removes everything built")

        re_ = ctx.run(["make", "re"], unit, timeout=240)
        if not re_.ok:
            yield result(None, "fail", "`make re` failed.", title=f"{prefix}`make re` rebuilds", log=re_.output)
        elif names and len(present()) != len(names):
            yield result(None, "fail", f"`make re` did not produce: {', '.join(set(names) - set(present()))}.", title=f"{prefix}`make re` rebuilds")
        else:
            yield result(None, "pass", "Rebuilt from scratch.", title=f"{prefix}`make re` rebuilds")
