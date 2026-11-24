from verdict.reviews.ai import BackendFactory, ClaudeCliBackend, OpenAIBackend, Settings


def test_the_factory_reads_the_mapping_it_is_given_not_the_process_environment():
    factory = BackendFactory(Settings({"LLM_PROVIDER": "claude-cli", "TERMINAL_URL": "http://terminal:8002", "TERMINAL_TOKEN": "tok", "CLAUDE_MODEL": "sonnet"}))
    made = factory.make("42/ps")
    assert isinstance(made, ClaudeCliBackend) and (made.repo, made.model) == ("42/ps", "sonnet")
    assert factory.provider().configured() and factory.provider().model_name() == "sonnet"


def test_each_provider_knows_its_own_model_and_host():
    openai = BackendFactory(Settings({"LLM_BASE_URL": "https://api.airforce/v1", "LLM_API_KEY": "k", "LLM_MODEL": " deepseek-v3 ",
                                      "LLM_FALLBACK_MODELS": "a, deepseek-v3, b", "LLM_STREAM": "1"})).provider()
    assert (openai.model_name(), openai.endpoint_host(), openai.configured()) == ("deepseek-v3", "api.airforce", True)
    assert openai.fallback_models() == ["a", "b"] and isinstance(openai.make(), OpenAIBackend) and openai.make().stream is True
    anthropic = BackendFactory(Settings({})).provider()
    assert (anthropic.model_name(), anthropic.endpoint_host(), anthropic.configured()) == ("claude-opus-5-5", "api.anthropic.com", False)
