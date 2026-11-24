"""Picking the backend the environment asks for, and the module-level shortcuts the web layer and the tests call."""

from __future__ import annotations

from verdict.reviews.ai.contract import Backend
from verdict.reviews.ai.settings.providers import PROVIDERS, Provider
from verdict.reviews.ai.settings.settings import Settings


class BackendFactory:
    """Factory: the provider that LLM_PROVIDER (or the presence of LLM_BASE_URL) selects, and the backend it makes."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def provider(self) -> Provider:
        return PROVIDERS[self.settings.provider_name()](self.settings)

    def make(self, repo: str = "") -> Backend:
        return self.provider().make(repo)


def provider() -> str:
    """"anthropic" (default), "openai" for any OpenAI-compatible endpoint, or "claude-cli" for the claude command in the terminal container."""
    return Settings().provider_name()


def model_name() -> str:
    return BackendFactory().provider().model_name()


def endpoint_host() -> str:
    return BackendFactory().provider().endpoint_host()


def fallback_models() -> list[str]:
    """Other models to try, in order, when the main one is unavailable (LLM_FALLBACK_MODELS=a,b)."""
    return BackendFactory().provider().fallback_models()


def streaming() -> bool:
    return Settings().streaming()


def configured() -> bool:
    return BackendFactory().provider().configured()


def make_client(repo: str = "") -> Backend:
    return BackendFactory().make(repo)
