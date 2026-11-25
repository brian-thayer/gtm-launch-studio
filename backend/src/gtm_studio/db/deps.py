"""FastAPI dependencies for database access.

They live in ``db/`` rather than ``api/`` because ``auth/deps.py`` needs them and infrastructure may not
import ``api``. ``api/deps.py`` re-exports ``get_session``. Build every service dependency on
``get_uow_factory`` rather than reading ``app.state`` (ADR-0006).
"""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from gtm_studio.services.ports import UnitOfWorkFactory


def get_session(request: Request) -> Iterator[Session]:
    """One session per request, closed afterwards. It never commits: reads are fine here, but a state
    change goes through a ``UnitOfWork`` so it commits (and audits) as one transaction."""
    session_factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError("no session factory: the app lifespan did not run (use `with TestClient(app)`)")
    with session_factory() as session:
        yield session


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    """The unit-of-work factory the app lifespan built. A service dependency takes it through
    ``Depends(get_uow_factory)``, so a test can override this one function."""
    uow_factory: UnitOfWorkFactory | None = getattr(request.app.state, "uow_factory", None)
    if uow_factory is None:
        raise RuntimeError(
            "no unit of work factory: the app lifespan did not run (use `with TestClient(app)`)"
        )
    return uow_factory
