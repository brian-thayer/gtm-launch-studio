"""A page of results from a cursor-paginated query. Pure: no IO, no framework."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Page[T]:
    """``items`` in display order, and the opaque ``next_cursor`` that continues after the last one
    (None when there is nothing more)."""

    items: list[T]
    next_cursor: str | None
