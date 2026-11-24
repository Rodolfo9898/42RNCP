"""The interchangeable ways to ask a model (Strategy family): the Anthropic API, an OpenAI-compatible server, claude in the terminal."""

from verdict.reviews.ai.backends.anthropic_api import AnthropicBackend
from verdict.reviews.ai.backends.claude_cli import ClaudeCliBackend
from verdict.reviews.ai.backends.openai_compatible import OpenAIBackend

__all__ = ["AnthropicBackend", "ClaudeCliBackend", "OpenAIBackend"]
