"""What can go wrong in a review, as the API reports it: the services raise these, the API turns them into `{"detail": message}`."""

from __future__ import annotations


class VerdictError(Exception):
    """An expected failure: it has a message for the person and an HTTP status for the API."""

    status = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(VerdictError):
    status = 404


class Conflict(VerdictError):
    status = 409


class TooLarge(VerdictError):
    status = 413


class Failed(VerdictError):
    status = 500


class Unavailable(VerdictError):
    status = 503
