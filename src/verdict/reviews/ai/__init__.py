"""AI-assisted review: describe what is in the repository and weigh the items a script cannot check.

Advisory only: nothing here changes a check result or the verdict. The model sees a bounded
digest of the repository (untrusted data), and every file/line it cites is verified against that
digest before it is shown, so an invented location is dropped rather than displayed.
"""

from verdict.reviews.ai.analysis import (
    SYSTEM, AnalysisOut, Analyst, CitationOut, CitationVerifier, ComponentOut, ImprovementOut, OverviewOut, ReviewItemOut,
    ReviewOut, analysis_task, analyze, review, review_task, verified,
)
from verdict.reviews.ai.backends import AnthropicBackend, ClaudeCliBackend, OpenAIBackend
from verdict.reviews.ai.backends.anthropic_api import MAX_TOKENS
from verdict.reviews.ai.backends.openai_compatible import LOCAL_HOSTS, reply_text
from verdict.reviews.ai.contract import AIError, Backend, BaseBackend, Cancelled, Job, ModelUnavailable, Usage, clean, extract_json
from verdict.reviews.ai.settings import (
    DEFAULT_MODEL, BackendFactory, Settings, configured, endpoint_host, fallback_models, make_client, model_name, provider, streaming,
)

__all__ = [
    "DEFAULT_MODEL", "LOCAL_HOSTS", "MAX_TOKENS", "SYSTEM", "AIError", "AnalysisOut", "Analyst", "AnthropicBackend", "Backend",
    "BackendFactory", "BaseBackend", "Cancelled", "CitationOut", "CitationVerifier", "ClaudeCliBackend", "ComponentOut", "ImprovementOut",
    "Job", "ModelUnavailable", "OpenAIBackend", "OverviewOut", "ReviewItemOut", "ReviewOut", "Settings", "Usage", "analysis_task",
    "analyze", "clean", "configured", "endpoint_host", "extract_json", "fallback_models", "make_client", "model_name", "provider",
    "reply_text", "review", "review_task", "streaming", "verified",
]
