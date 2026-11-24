"""The three places a review can be asked, each knowing its model, its host, whether it is set up, and how to make its backend."""

from __future__ import annotations

import anthropic

from verdict.reviews.ai.backends import AnthropicBackend, ClaudeCliBackend, OpenAIBackend
from verdict.reviews.ai.backends.openai_compatible import Endpoint
from verdict.reviews.ai.contract import Backend
from verdict.reviews.ai.settings.settings import Settings

DEFAULT_MODEL = "claude-opus-5-5"


class Provider:
    """Strategy (one subclass per provider): what the environment says about it, and the backend it builds."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def model_name(self) -> str:
        raise NotImplementedError

    def endpoint_host(self) -> str:
        raise NotImplementedError

    def configured(self) -> bool:
        raise NotImplementedError

    def make(self, repo: str = "") -> Backend:
        raise NotImplementedError

    def fallback_models(self) -> list[str]:
        return self.settings.fallback_models(self.model_name())


class AnthropicProvider(Provider):
    def model_name(self) -> str:
        return self.settings.get("LLM_MODEL") or DEFAULT_MODEL

    def endpoint_host(self) -> str:
        return "api.anthropic.com"

    def configured(self) -> bool:
        return bool(self.settings.get("ANTHROPIC_API_KEY") or self.settings.get("ANTHROPIC_AUTH_TOKEN"))

    def make(self, repo: str = "") -> Backend:
        return AnthropicBackend(anthropic.Anthropic(), self.model_name())


class OpenAIProvider(Provider):
    def _endpoint(self) -> Endpoint:
        return Endpoint(self.settings.text("LLM_BASE_URL"))

    def model_name(self) -> str:
        return self.settings.text("LLM_MODEL")

    def endpoint_host(self) -> str:
        return Endpoint(self.settings.get("LLM_BASE_URL")).host or "?"

    def configured(self) -> bool:
        endpoint = self._endpoint()
        has_key = bool(self.settings.text("LLM_API_KEY"))
        return bool(endpoint.base_url and self.model_name() and (has_key or endpoint.local))

    def make(self, repo: str = "") -> Backend:
        return OpenAIBackend(self.settings.environ["LLM_BASE_URL"].strip(), self.settings.text("LLM_API_KEY"), self.model_name(),
                             fallbacks=self.fallback_models(), stream=self.settings.streaming())


class ClaudeCliProvider(Provider):
    def model_name(self) -> str:
        return self.settings.text("CLAUDE_MODEL") or "account default"      # (never LLM_MODEL: that names another backend's model)

    def endpoint_host(self) -> str:
        return "Claude Code (your Claude login)"

    def configured(self) -> bool:
        return bool(self.settings.get("TERMINAL_URL") and self.settings.get("TERMINAL_TOKEN"))

    def make(self, repo: str = "") -> Backend:
        return ClaudeCliBackend(self.settings.environ["TERMINAL_URL"], self.settings.environ["TERMINAL_TOKEN"], repo,
                                self.settings.text("CLAUDE_MODEL"))


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "claude-cli": ClaudeCliProvider}
