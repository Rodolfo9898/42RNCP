"""What every checker is handed: the repository, the rules of the review and the sandbox, behind one object."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verdict.checks.context.build_result import BuildResult
from verdict.checks.context.builds import Builds
from verdict.checks.context.layout import Layout
from verdict.checks.context.repo_files import RepoFiles
from verdict.core.models import Rule, Section
from verdict.gateways.sandbox import ExecResult, Sandbox


@dataclass
class Ctx:
    """The review of one repository (Facade over RepoFiles, Layout and Builds, which hold the logic). `cache` is shared by the
    three: what is computed once per review is kept there, and the web app may seed it (`submodule_notes`)."""

    repo: Path
    rules: list[Rule]
    sandbox: Sandbox | None
    lang: str | None = None
    cache: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tree = RepoFiles(self.repo, self.cache)
        self.layout = Layout(self.repo, self.rules, self.cache)
        self.builds = Builds(self.repo, self.sandbox, self.layout, self.cache)

    # ---- repo helpers
    def files(self) -> list[Path]:
        return self.tree.files()

    def source_files(self, unit: str = ".", *, exclude_vendored: bool = True) -> list[Path]:
        return self.tree.source_files(unit, exclude_vendored=exclude_vendored)

    def read(self, rel: Path) -> str:
        return self.tree.read(rel)

    def walk(self, base: Path) -> list[Path]:
        return self.tree.walk(base)

    def is_vendored(self, rel: Path | str) -> bool:
        return self.tree.is_vendored(rel)

    def minilibx_dirs(self) -> list[str]:
        return self.tree.minilibx_dirs()

    def student_submodule_files(self) -> list[Path]:
        return self.tree.student_submodule_files()

    def submodule_paths(self) -> list[str]:
        return self.tree.submodule_paths()

    def has_bonus(self) -> bool:
        return self.tree.has_bonus()

    # ---- layout and rules helpers
    @property
    def strict_layout(self) -> bool:
        return self.layout.strict

    def unit_dir(self, unit: str) -> Path:
        return self.layout.unit_dir(unit)

    def moved_unit(self, unit: str) -> str:
        return self.layout.moved_unit(unit)

    def units(self) -> list[str]:
        return self.layout.units()

    def programs(self, unit: str, section: Section | None = None) -> list[str]:
        return self.layout.programs(unit, section)

    def has_makefile(self, unit: str) -> bool:
        return self.layout.has_makefile(unit)

    # ---- sandbox helpers
    def run(self, argv: list[str], unit: str = ".", timeout: float = 60, stdin: str = "") -> ExecResult:
        return self.builds.run(argv, unit, timeout, stdin)

    def build(self, unit: str, bonus: bool = False) -> BuildResult:
        return self.builds.build(unit, bonus)

    def offline_reason(self, build: BuildResult) -> str:
        return self.builds.offline_reason(build)

    def executables(self, unit: str) -> list[Path]:
        return self.builds.executables(unit)

    def libraries(self, unit: str) -> list[Path]:
        return self.builds.libraries(unit)
