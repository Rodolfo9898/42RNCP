"""The terminal container's `claude -p` as a backend, reached through the terminal service."""

from __future__ import annotations

import time

import httpx

from verdict.reviews.ai.backends.claude_cli.output import ClaudeOutput
from verdict.reviews.ai.contract import AIError, BaseBackend, Cancelled, clean


class ClaudeCliBackend(BaseBackend):
    """Strategy + Gateway: runs `claude -p` in the terminal container (read-only tools, signed in with the user's own Claude login).

    Claude explores the repository itself with Read/Grep/Glob, so no digest is sent from here.
    """

    batch = 15
    TIMEOUT = 900

    def __init__(self, url: str, token: str, repo: str, model: str = "", http_factory=None):
        super().__init__()
        self.base, self.token, self.repo, self.model = url.rstrip("/"), token, repo, model
        self.http_factory = http_factory or (lambda: httpx.Client(timeout=httpx.Timeout(self.TIMEOUT + 60, connect=10.0), trust_env=False))

    def structured(self, system, digest_text, task, schema, usage):
        self._check()
        prompt = (f"{system}\n\nYou have no file listing. Explore the repository in the current directory with the Read, Grep and "
                  f"Glob tools (Read shows line numbers; cite those), then answer.\n\n{task}")
        self.job.notify("Asking claude (your login) to read the repository… this can take a few minutes")
        started = time.monotonic()
        response = self._post(prompt, schema)
        self.job.notify(f"claude finished after {time.monotonic() - started:.0f}s")
        self._refuse_errors(response)
        return ClaudeOutput(response.json(), usage).parse(schema)

    def _post(self, prompt: str, schema) -> httpx.Response:
        client = self.http_factory()
        try:
            return self._cancellable(lambda: client.post(
                f"{self.base}/reviews", headers={"x-terminal-token": self.token},
                json={"repo": self.repo, "prompt": prompt, "schema": schema.model_json_schema(),
                      "model": self.model or None, "timeout": self.TIMEOUT}))
        except Cancelled:
            client.close()  # dropping the connection makes the terminal service stop claude
            raise
        except httpx.TimeoutException as exc:
            raise AIError("claude did not finish in time.") from exc
        except httpx.HTTPError as exc:
            raise AIError("Could not reach the terminal service (is it running? start everything with `make run`).") from exc
        finally:
            client.close()

    @staticmethod
    def _refuse_errors(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise AIError("The terminal service rejected the request (TERMINAL_TOKEN mismatch: restart with `make run`).")
        if response.status_code == 504:
            raise AIError("claude did not finish in time. Try again, or use a smaller repository.")
        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = None
            raise AIError("The terminal service refused the review: " + clean(str((detail or {}).get("detail", response.status_code)), 200))
