"""The exceptions services raise for an expected refusal (ADR-0006). Pure: no IO, no framework.

``api/errors.py`` maps each subclass to one HTTP status, so a router never catches them itself. ``detail``
goes to the client as it is: keep it short and safe, never request data, personal data or secrets.
"""


class DomainError(Exception):
    """Base class. Raise a subclass: a bare ``DomainError`` has no status and surfaces as a 500."""

    detail: str

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    """The thing asked for doesn't exist (404)."""


class ConflictError(DomainError):
    """The change clashes with the current state (409)."""


class InvalidInputError(DomainError):
    """The request is well-formed but its values can't be used (422)."""


class NotPermittedError(DomainError):
    """The actor may not do this to this thing, beyond the route's permission check (403)."""
