"""FastAPI dependency for database access.

It lives in ``db/`` rather than ``api/`` because ``auth/deps.py`` needs it and infrastructure may not
import ``api``. ``api/deps.py`` re-exports it.
"""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker


def get_session(request: Request) -> Iterator[Session]:
    """One session per request, closed afterwards. It never commits: reads are fine here, but a state
    change goes through a ``UnitOfWork`` so it commits (and audits) as one transaction."""
    session_factory: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise RuntimeError("no session factory: the app lifespan did not run (use `with TestClient(app)`)")
    with session_factory() as session:
        yield session
