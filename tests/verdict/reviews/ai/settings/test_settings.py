import json

import pytest

from verdict.reviews import ai
from tests.verdict.reviews.ai.backends.openai_compatible.fakes import KEY


def test_anthropic_configuration(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert not ai.configured()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert ai.configured()
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert ai.model_name() == "claude-opus-5-5"
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5-5")
    assert ai.model_name() == "claude-sonnet-5-5"


def test_claude_cli_configuration(monkeypatch):
    for name in ("TERMINAL_URL", "TERMINAL_TOKEN", "LLM_MODEL", "CLAUDE_MODEL", "LLM_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    assert ai.provider() == "claude-cli" and not ai.configured()
    monkeypatch.setenv("TERMINAL_URL", "http://terminal:8002")
    monkeypatch.setenv("TERMINAL_TOKEN", "tok")
    assert ai.configured() and ai.model_name() == "account default" and "Claude" in ai.endpoint_host()
    made = ai.make_client(repo="42/ps")
    assert isinstance(made, ai.ClaudeCliBackend) and made.repo == "42/ps" and made.model == ""
    monkeypatch.setenv("CLAUDE_MODEL", "sonnet")
    assert ai.make_client(repo="x").model == "sonnet" and ai.model_name() == "sonnet"


def test_another_backends_model_name_never_reaches_claude(monkeypatch):
    """A leftover LLM_MODEL=ministral-14b-latest (for an OpenAI-compatible server) used to be passed as claude's --model."""
    for name in ("CLAUDE_MODEL", "LLM_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    monkeypatch.setenv("TERMINAL_URL", "http://terminal:8002")
    monkeypatch.setenv("TERMINAL_TOKEN", "tok")
    monkeypatch.setenv("LLM_MODEL", "ministral-14b-latest")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "llama-instant")
    assert ai.model_name() == "account default" and ai.make_client(repo="x").model == ""


# ---------------------------------------------------------------- configuration


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_base_url_selects_the_openai_compatible_provider(clean_env):
    assert ai.provider() == "anthropic" and not ai.configured()
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    assert ai.provider() == "openai"
    assert not ai.configured()                                 # still needs a key and a model
    clean_env.setenv("LLM_API_KEY", KEY)
    assert not ai.configured()
    clean_env.setenv("LLM_MODEL", "deepseek-v3")
    assert ai.configured() and ai.model_name() == "deepseek-v3" and ai.endpoint_host() == "api.airforce"


def test_a_local_server_needs_no_key(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1")
    clean_env.setenv("LLM_MODEL", "llama3.1")
    assert ai.configured()


def test_an_anthropic_key_alone_keeps_the_default_provider(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "k")
    assert ai.provider() == "anthropic" and ai.configured() and ai.endpoint_host() == "api.anthropic.com"
    clean_env.setenv("LLM_PROVIDER", "openai")
    assert not ai.configured()                                 # explicitly asked for the other provider, which is not set up


def test_make_client_builds_the_selected_backend(clean_env):
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    clean_env.setenv("LLM_API_KEY", KEY)
    clean_env.setenv("LLM_MODEL", "deepseek-v3")
    backend_ = ai.make_client()
    assert isinstance(backend_, ai.OpenAIBackend) and backend_.url == "https://api.airforce/v1/chat/completions"
    clean_env.delenv("LLM_BASE_URL")
    clean_env.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(ai.make_client(), ai.AnthropicBackend)


def test_fallback_models_come_from_the_environment(clean_env):
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    clean_env.setenv("LLM_API_KEY", KEY)
    clean_env.setenv("LLM_MODEL", "glm-4.7-flash")
    clean_env.setenv("LLM_FALLBACK_MODELS", " gpt-oss-20b, glm-4.7-flash ,mistral-large-latest,,")
    assert ai.fallback_models() == ["gpt-oss-20b", "mistral-large-latest"]     # the main model is not repeated
    made = ai.make_client()
    assert made.model == "glm-4.7-flash" and made.fallbacks == ["gpt-oss-20b", "mistral-large-latest"]


def test_streaming_is_switched_on_from_the_environment(clean_env):
    clean_env.setenv("LLM_BASE_URL", "https://api.airforce/v1")
    clean_env.setenv("LLM_API_KEY", KEY)
    clean_env.setenv("LLM_MODEL", "m")
    assert ai.make_client().stream is False
    clean_env.setenv("LLM_STREAM", "true")
    assert ai.make_client().stream is True
