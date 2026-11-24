"""What the environment says about the AI backend, and the factory that builds it."""

from verdict.reviews.ai.settings.facade import (
    BackendFactory, configured, endpoint_host, fallback_models, make_client, model_name, provider, streaming,
)
from verdict.reviews.ai.settings.providers import DEFAULT_MODEL, PROVIDERS, Provider
from verdict.reviews.ai.settings.settings import Settings

__all__ = ["DEFAULT_MODEL", "PROVIDERS", "BackendFactory", "Provider", "Settings", "configured", "endpoint_host", "fallback_models",
           "make_client", "model_name", "provider", "streaming"]
