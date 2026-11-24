"""The SQLAlchemy implementation of the ``UnitOfWork`` port (``services/ports.py``)."""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from gtm_studio.db.repositories.identity import SqlIdentityRepository


class SqlUnitOfWork:
    """A transaction around one ``Session``: commit on a clean exit, roll back on an exception.

    >>> with SqlUnitOfWork(session_factory) as uow:
    ...     uow.session.add(...)

    Repositories are built over ``session`` and exposed as properties (``identity``). Not reusable
    while entered, and not thread-safe: make one per use case through a ``UnitOfWorkFactory``.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("the unit of work is not active: use it in a `with` block")
        return self._session

    @property
    def identity(self) -> SqlIdentityRepository:
        return SqlIdentityRepository(self.session)

    def __enter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("the unit of work is already active")
        self._session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
        /,
    ) -> None:
        session = self.session
        self._session = None
        try:
            if exc_type is None:
                session.commit()
            else:
                session.rollback()
        finally:
            session.close()  # also rolls back anything left uncommitted when the commit itself failed
