"""The environment as the AI review reads it: the one place that knows the names of the variables."""

from __future__ import annotations

import os
from collections.abc import Mapping

PROVIDER_NAMES = ("anthropic", "openai", "claude-cli")


class Settings:
    """Facade over the environment (LLM_*, ANTHROPIC_*, CLAUDE_MODEL, TERMINAL_*), read when asked so that a change is seen."""

    def __init__(self, environ: Mapping[str, str] | None = None):
        self.environ = os.environ if environ is None else environ

    def get(self, name: str) -> str:
        return self.environ.get(name, "")

    def text(self, name: str) -> str:
        return self.get(name).strip()

    def provider_name(self) -> str:
        """"anthropic" (default), "openai" for any OpenAI-compatible endpoint, or "claude-cli" for the claude command in the terminal container."""
        chosen = self.text("LLM_PROVIDER").lower()
        if chosen in PROVIDER_NAMES:
            return chosen
        return "openai" if self.get("LLM_BASE_URL") else "anthropic"

    def streaming(self) -> bool:
        return self.text("LLM_STREAM").lower() in ("1", "true", "yes", "on")

    def fallback_models(self, main_model: str) -> list[str]:
        """Other models to try, in order, when the main one is unavailable (LLM_FALLBACK_MODELS=a,b)."""
        return [m.strip() for m in self.get("LLM_FALLBACK_MODELS").split(",") if m.strip() and m.strip() != main_model]
