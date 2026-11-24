"""Composition root of the sandbox runner: reads the environment once, wires the pieces, serves."""

import threading
from collections.abc import Mapping

from sandbox.display.xvfb import VirtualDisplay
from sandbox.execution.command import CommandRunner
from sandbox.execution.environment import CommandEnvironment
from sandbox.execution.limits import ResourceLimits
from sandbox.request.roots import AllowedRoots
from sandbox.request.validator import RequestValidator
from sandbox.service.exec_service import ExecService
from sandbox.service.handler import RunnerServer

MAX_TIMEOUT = 300
PORT = 8001


def build_service(environ: Mapping[str, str], display: VirtualDisplay) -> ExecService:
    validator = RequestValidator(AllowedRoots.from_environment(environ), MAX_TIMEOUT)
    runner = CommandRunner(CommandEnvironment.from_environment(environ, display), ResourceLimits(cpu_seconds=MAX_TIMEOUT))
    return ExecService(validator, runner)


def serve(environ: Mapping[str, str]) -> None:
    """Never run this directly on a host: it executes whatever it is sent. 0.0.0.0 is only safe because the container sits on an
    internal Docker network (see docker-compose.yml)."""
    display = VirtualDisplay()
    threading.Thread(target=display.environment, daemon=True).start()      # (so that the first program does not wait for the display)
    server = RunnerServer((environ.get("RUNNER_HOST", "0.0.0.0"), PORT), build_service(environ, display))
    try:
        server.serve_forever()
    finally:
        display.stop()
