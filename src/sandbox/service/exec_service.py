"""POST /exec without the HTTP: a body in, a status and an answer out."""

import json

from sandbox.execution.command import CommandRunner, ExecResult
from sandbox.request.validator import RequestValidator


class ExecService:
    """Facade over validation and execution: refuses a bad body (400) before anything runs, answers 200 for everything that ran.

    POST /exec {"argv": [...], "cwd": "/workspace/...", "timeout": 60, "stdin": "", "env": {"SUBJECTS_DIR": "..."}}
             -> {"rc": int, "stdout": str, "stderr": str, "timed_out": bool, "truncated": bool}"""

    def __init__(self, validator: RequestValidator, runner: CommandRunner) -> None:
        self.validator, self.runner = validator, runner

    def handle(self, raw: bytes) -> tuple[int, dict]:
        try:
            request = self.validator.parse(json.loads(raw))
        except (KeyError, ValueError, TypeError) as exc:      # (a body that is not JSON is a ValueError too)
            return 400, {"error": str(exc)}
        try:
            return 200, self.runner.run(request).as_dict()
        except OSError as exc:  # e.g. executable not found
            return 200, ExecResult.not_started(exc).as_dict()
