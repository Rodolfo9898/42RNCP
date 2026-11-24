"""What a request to run a command may ask for. Nothing here runs anything: it only says yes (with a clean value) or raises ValueError."""

from dataclasses import dataclass, field
from pathlib import Path

from sandbox.request.roots import AllowedRoots


@dataclass(frozen=True)
class ExecRequest:
    argv: list[str]
    cwd: Path
    timeout: float
    stdin: str
    env: dict[str, str] = field(default_factory=dict)


class RequestValidator:
    """Turns the JSON body of POST /exec into an ExecRequest, or refuses it.

    {"argv": [...], "cwd": "/workspace/...", "timeout": 60, "stdin": "", "env": {"SUBJECTS_DIR": "/workspace/<id>/subjects"}}

    The only variables a request may add to the clean environment of the commands are `extra_env_keys`, each pointing at an existing
    folder inside the allowed roots: SUBJECTS_DIR is where the PDFs of the review (the subjects, and the Norm when it applies) are."""

    def __init__(self, roots: AllowedRoots, max_timeout: float, extra_env_keys: frozenset[str] = frozenset({"SUBJECTS_DIR"})) -> None:
        self.roots, self.max_timeout, self.extra_env_keys = roots, max_timeout, extra_env_keys

    def parse(self, body: dict) -> ExecRequest:
        argv = body["argv"]
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
            raise ValueError("argv must be a non-empty list of strings")
        cwd = self.roots.existing_directory(body["cwd"], "cwd")
        timeout = min(float(body.get("timeout", 60)), self.max_timeout)
        return ExecRequest(argv, cwd, timeout, str(body.get("stdin", "")), self.parse_env(body))

    def parse_env(self, body: dict) -> dict[str, str]:
        """The extra environment of a request: only the variables allowed, only folders that exist inside the allowed roots."""
        extra = body.get("env") or {}
        if not isinstance(extra, dict):
            raise ValueError("env must be an object")
        parsed: dict[str, str] = {}
        for key, value in extra.items():
            if key not in self.extra_env_keys or not isinstance(value, str):
                raise ValueError(f"{key!r} cannot be set")
            parsed[key] = str(self.roots.existing_directory(value, key))
        return parsed
