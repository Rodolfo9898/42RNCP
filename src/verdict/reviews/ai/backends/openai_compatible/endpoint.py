"""The address of an OpenAI-compatible server, and the rules about which ones may be used."""

from __future__ import annotations

from urllib.parse import urlparse

from verdict.reviews.ai.contract import AIError

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


class Endpoint:
    """The base URL of the server (LLM_BASE_URL), checked: https, except for a server on this machine."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.host = urlparse(base_url).hostname or ""

    @property
    def local(self) -> bool:
        return self.host in LOCAL_HOSTS

    def validated(self) -> "Endpoint":
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise AIError("LLM_BASE_URL must be a URL such as https://api.example.com/v1.")
        if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS:
            raise AIError("LLM_BASE_URL must use https:// (plain http is only allowed for a local server).")
        return self

    @property
    def chat_completions(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"
