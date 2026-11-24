"""The one error every repository operation raises: its message is safe to show to the user."""

from __future__ import annotations


class RepoError(ValueError):
    pass
