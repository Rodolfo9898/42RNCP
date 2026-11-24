"""The HTTP side of the runner: GET /health and POST /exec, over the standard library's server."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sandbox.service.exec_service import ExecService

MAX_BODY = 1_000_000


class RunnerServer(ThreadingHTTPServer):
    """The server that holds what its handlers need (they are made anew for each request, so they reach it through `self.server`)."""

    def __init__(self, address: tuple[str, int], service: ExecService, max_body: int = MAX_BODY) -> None:
        super().__init__(address, RunnerHandler)
        self.service, self.max_body = service, max_body


class RunnerHandler(BaseHTTPRequestHandler):
    """Adapter from HTTP to ExecService: it reads and writes, and decides nothing about the command."""

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
        except ValueError as exc:
            return self._send(400, {"error": str(exc)})
        if length > self.server.max_body:
            return self._send(413, {"error": "body too large"})
        self._send(*self.server.service.handle(self.rfile.read(length)))

    def log_message(self, fmt: str, *args) -> None:
        pass
