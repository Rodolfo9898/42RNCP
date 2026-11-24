"""What norminette says about the student's code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from verdict.checks.context.ctx import Ctx
from verdict.checks.context.memo import memo

BATCH = 100                 # files per norminette run
ANSI = re.compile(r"\x1b\[[0-9;]*m")
FILE_LINE = re.compile(r"^(\S+): (OK!|Error!)$")
ERROR_LINE = re.compile(r"^(Error|Notice): (\w+)\s+\(line:\s*(\d+), col:\s*(\d+)\):\s*(.*)$")


class NormError(NamedTuple):
    code: str
    line: int
    message: str
    kind: str               # "Error" counts against the project, "Notice" does not


@dataclass
class NormReport:
    """norminette run once over the student's C files; read by the Norm check and by the global variables check."""

    files: int
    errors: dict[str, list[NormError]] = field(default_factory=dict)
    available: bool = True

    @classmethod
    def collect(cls, ctx: Ctx) -> NormReport:
        # The student's own code: the project, plus the submodules they wrote (their libft...). MiniLibX is given to them, so it is left out.
        files = [p.as_posix() for p in ctx.source_files(".") if p.suffix in (".c", ".h")]
        files += [p.as_posix() for p in ctx.student_submodule_files() if p.as_posix() not in files]
        report = cls(len(files))
        for start in range(0, len(files), BATCH):
            res = ctx.run(["norminette", *files[start:start + BATCH]], ".", timeout=180)
            if res.rc == 127:
                report.available = False
                break
            report.read(res.stdout)
        return report

    def read(self, output: str) -> None:
        current = None
        for line in output.splitlines():
            line = ANSI.sub("", line)
            m = FILE_LINE.match(line)
            if m:
                current = m.group(1)
                continue
            m = ERROR_LINE.match(line)
            if m and current:
                self.errors.setdefault(current, []).append(NormError(m.group(2), int(m.group(3)), m.group(5), m.group(1)))


def norm_report(ctx: Ctx) -> NormReport:
    return memo(ctx.cache, "norm", lambda: NormReport.collect(ctx))
