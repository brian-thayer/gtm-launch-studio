from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from gtm_studio.db.engine import SQLITE_BUSY_TIMEOUT_MS, make_engine, make_session_factory
from gtm_studio.db.models import AppMeta
from gtm_studio.db.uow import SqlUnitOfWork
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import Settings


def _pragma(engine: Engine, name: str) -> object:
    with engine.connect() as connection:
        return connection.exec_driver_sql(f"PRAGMA {name}").scalar_one()


def test_sqlite_connections_use_wal_foreign_keys_and_a_busy_timeout(migrated_engine: Engine) -> None:
    assert _pragma(migrated_engine, "journal_mode") == "wal"
    assert _pragma(migrated_engine, "foreign_keys") == 1
    assert _pragma(migrated_engine, "busy_timeout") == SQLITE_BUSY_TIMEOUT_MS


def test_make_engine_creates_the_database_folder(tmp_path: Path) -> None:
    nested = tmp_path / "does" / "not" / "exist" / "app.db"
    engine = make_engine(Settings(env="test", db_url=f"sqlite:///{nested.as_posix()}"))
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
    assert nested.is_file()


def test_make_engine_accepts_an_in_memory_database() -> None:
    engine = make_engine(Settings(env="test", db_url="sqlite://"))
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return make_session_factory(migrated_engine)


def _value(session_factory: sessionmaker[Session], key: str) -> str | None:
    with session_factory() as session:
        row = session.get(AppMeta, key)
        return row.value if row else None


def test_unit_of_work_commits_on_a_clean_exit(session_factory: sessionmaker[Session]) -> None:
    with SqlUnitOfWork(session_factory) as uow:
        uow.session.add(AppMeta(key="greeting", value="hello"))
    assert _value(session_factory, "greeting") == "hello"


def test_unit_of_work_rolls_back_on_an_exception(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError, match="boom"), SqlUnitOfWork(session_factory) as uow:
        uow.session.add(AppMeta(key="greeting", value="hello"))
        uow.session.flush()  # the INSERT is sent, so only a rollback can make it disappear
        raise RuntimeError("boom")
    assert _value(session_factory, "greeting") is None


def test_unit_of_work_session_is_only_available_inside_the_block(
    session_factory: sessionmaker[Session],
) -> None:
    uow = SqlUnitOfWork(session_factory)
    with pytest.raises(RuntimeError, match="not active"):
        uow.session  # noqa: B018
    with uow, pytest.raises(RuntimeError, match="already active"), uow:
        pass
    with pytest.raises(RuntimeError, match="not active"):
        uow.session  # noqa: B018


def test_the_unit_of_work_satisfies_the_services_port(session_factory: sessionmaker[Session]) -> None:
    """pyright checks this assignment: db/uow.py must stay compatible with services/ports.py."""
    factory: UnitOfWorkFactory = lambda: SqlUnitOfWork(session_factory)  # noqa: E731
    with factory():
        pass
