"""Engine and session-factory construction. Nothing here runs at import time."""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from gtm_studio.settings import Settings

SQLITE_BUSY_TIMEOUT_MS = 5000


def _set_sqlite_pragmas(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
    """Per-connection settings. WAL lets readers and the one writer overlap (ADR-0001); foreign keys are
    off by default in SQLite and must be switched on for every connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def sqlite_file(url: URL) -> Path | None:
    """The file behind a file-based SQLite URL. None for other backends, in-memory and URI databases."""
    database = url.database
    if url.get_backend_name() != "sqlite" or not database:
        return None
    if database == ":memory:" or database.startswith("file:"):
        return None
    return Path(database)


def make_engine(settings: Settings) -> Engine:
    """Build the engine for ``settings.db_url``. For a SQLite file, create its folder first."""
    url = make_url(settings.db_url)
    connect_args: dict[str, Any] = {}
    is_sqlite = url.get_backend_name() == "sqlite"
    if is_sqlite:
        # Requests run in a thread pool and the pool hands a connection to whichever thread asks.
        connect_args["check_same_thread"] = False
        db_file = sqlite_file(url)
        if db_file is not None:
            db_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args=connect_args)
    if is_sqlite:
        event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: services return ORM objects after the unit of work commits, and
    # reloading every attribute on first access would be a surprise query (and an error once closed).
    return sessionmaker(engine, expire_on_commit=False)


def database_is_up(session: Session) -> bool:
    """True when the database answers ``SELECT 1``. For the health check: it never raises."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
