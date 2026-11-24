"""How an AI review can end badly. Every message is safe to show to the user (no key, no request, no repository text)."""

from __future__ import annotations


class AIError(RuntimeError):
    """A failure whose message is safe to show to the user."""


class Cancelled(AIError):
    """The user stopped the review."""


class ModelUnavailable(AIError):
    """This model cannot serve the request right now (down, overloaded, unknown or unpaid): another one might."""
