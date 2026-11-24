"""Where a command may run: only inside the folders the operator allowed (the shared workspace)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


class AllowedRoots:
    """The roots under which a request may name a folder. Every folder a request mentions is checked here, in one place."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [Path(root).resolve() for root in roots]

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> AllowedRoots:
        listed = environ.get("ALLOWED_ROOTS", environ.get("WORKSPACE", "/workspace"))
        return cls([Path(root) for root in listed.split(":") if root])

    def existing_directory(self, value: str, what: str) -> Path:
        """`value`, resolved (so `..` and links cannot leave the roots), when it is an existing directory inside a root."""
        folder = Path(value).resolve()
        if not any(folder.is_relative_to(root) for root in self.roots) or not folder.is_dir():
            raise ValueError(f"{what} must be an existing directory inside an allowed root")
        return folder
