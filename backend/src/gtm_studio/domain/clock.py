"""The one place the application reads the wall clock (ADR-0006). ``db.base`` re-exports it."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Now, as a timezone-aware UTC datetime."""
    return datetime.now(UTC)
