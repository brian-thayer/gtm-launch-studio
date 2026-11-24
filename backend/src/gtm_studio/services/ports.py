"""Ports: the interfaces services depend on. ``db`` and ``adapters`` implement them.

Services never import ``gtm_studio.db`` (the layers contract forbids an upward import), so nothing in
this file may mention SQLAlchemy. S06 adds the repository ports here.
"""

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self


class UnitOfWork(Protocol):
    """One transaction. Entering it opens the work, leaving it cleanly commits, and leaving it with an
    exception rolls back. Repository ports are attached to it as attributes (S06)."""

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
        /,
    ) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
