"""The backend for any server that speaks the OpenAI chat-completions protocol."""

from verdict.reviews.ai.backends.openai_compatible.backend import OpenAIBackend
from verdict.reviews.ai.backends.openai_compatible.endpoint import LOCAL_HOSTS, Endpoint
from verdict.reviews.ai.backends.openai_compatible.replies import Reply, reply_text, summarise_reply

__all__ = ["LOCAL_HOSTS", "Endpoint", "OpenAIBackend", "Reply", "reply_text", "summarise_reply"]
