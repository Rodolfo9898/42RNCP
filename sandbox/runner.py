"""Tiny command runner for untrusted repositories.

Stdlib only. Runs inside the `sandbox` container, which has no outbound network
(see docker-compose.yml). Only the web app can reach it, over an internal network.

POST /exec  {"argv": [...], "cwd": "/workspace/...", "timeout": 60, "stdin": ""}
         -> {"rc": int, "stdout": str, "stderr": str, "timed_out": bool, "truncated": bool}
GET  /health
"""

import json
import os
import resource
import signal
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOTS = [Path(r).resolve() for r in os.environ.get("ALLOWED_ROOTS", os.environ.get("WORKSPACE", "/workspace")).split(":") if r]
MAX_TIMEOUT = 300
MAX_OUTPUT = 1_000_000  # bytes kept per stream
MAX_BODY = 1_000_000

ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "TMPDIR": "/tmp",
    "DOCKER_CONFIG": "/tmp/.docker",
}
# The sandbox has a Docker client but no daemon. If an operator deliberately points the runner at one, commands run
# by the review can use it; nothing is passed on otherwise (and the host's socket is never mounted).
if os.environ.get("DOCKER_HOST"):
    ENV["DOCKER_HOST"] = os.environ["DOCKER_HOST"]


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))
    resource.setrlimit(resource.RLIMIT_CPU, (MAX_TIMEOUT, MAX_TIMEOUT))


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass  # already gone (macOS reports EPERM for a group that only holds zombies)


def run(argv: list[str], cwd: Path, timeout: float, stdin: str) -> dict:
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=ENV,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        preexec_fn=_limits,
    )
    timed_out = False
    try:
        out, err = proc.communicate(stdin.encode(), timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc.pid)
        out, err = proc.communicate()
    finally:
        _kill_group(proc.pid)  # reap anything the command left behind
    return {
        "rc": proc.returncode,
        "stdout": out[:MAX_OUTPUT].decode(errors="replace"),
        "stderr": err[:MAX_OUTPUT].decode(errors="replace"),
        "timed_out": timed_out,
        "truncated": len(out) > MAX_OUTPUT or len(err) > MAX_OUTPUT,
    }


def parse_request(req: dict) -> tuple[list[str], Path, float, str]:
    argv = req["argv"]
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        raise ValueError("argv must be a non-empty list of strings")
    cwd = Path(req["cwd"]).resolve()
    if not any(cwd.is_relative_to(root) for root in ROOTS) or not cwd.is_dir():
        raise ValueError("cwd must be an existing directory inside an allowed root")
    return argv, cwd, min(float(req.get("timeout", 60)), MAX_TIMEOUT), str(req.get("stdin", ""))


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/exec":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY:
                return self._send(413, {"error": "body too large"})
            argv, cwd, timeout, stdin = parse_request(json.loads(self.rfile.read(length)))
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._send(400, {"error": str(exc)})
        try:
            self._send(200, run(argv, cwd, timeout, stdin))
        except OSError as exc:  # e.g. executable not found
            self._send(200, {"rc": 127, "stdout": "", "stderr": str(exc),
                             "timed_out": False, "truncated": False})

    def log_message(self, fmt: str, *args) -> None:
        pass


if __name__ == "__main__":
    # 0.0.0.0 is only safe because the container sits on an internal Docker network.
    # Never run this directly on a host: it executes whatever it is sent.
    ThreadingHTTPServer((os.environ.get("RUNNER_HOST", "0.0.0.0"), 8001), Handler).serve_forever()
