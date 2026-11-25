"""Shared fixtures. Tests never read the developer's real backend/.env or GTM_* environment."""

import json
import logging
import os
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from gtm_studio.api.app import create_app
from gtm_studio.api.introspection import RouteInfo, list_routes
from gtm_studio.audit.logging import QUIET_LIBRARIES, StderrHandler, configure_logging
from gtm_studio.db.engine import make_engine, make_session_factory
from gtm_studio.db.migrate import upgrade
from gtm_studio.db.uow import SqlUnitOfWork
from gtm_studio.services.identity import IdentityService, SeedSummary
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import REPO_ROOT, Settings


@pytest.fixture(autouse=True)
def _isolate_settings_from_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's shell and backend/.env out of every test.

    Removes the GTM_* variables and turns off the .env file at the class level. (Not ``_env_file=None``
    per call: pyright drops pydantic-settings' underscore keyword arguments.)
    """
    for name in [n for n in os.environ if n.startswith("GTM_")]:
        monkeypatch.delenv(name)
    monkeypatch.setitem(Settings.model_config, "env_file", None)


_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """``configure_logging`` (called by app start-up and the CLI) changes process-wide state. Put it back
    after every test, so one test's logging setup never reaches the next."""
    root = logging.getLogger()
    level = root.level
    servers = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in _SERVER_LOGGERS
    }
    library_levels = {name: logging.getLogger(name).level for name in QUIET_LIBRARIES}
    yield
    structlog.reset_defaults()
    root.handlers[:] = [h for h in root.handlers if not isinstance(h, StderrHandler)]
    root.setLevel(level)
    for name, (handlers, propagate) in servers.items():
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate
    for name, library_level in library_levels.items():
        logging.getLogger(name).setLevel(library_level)


@pytest.fixture
def stderr_logs(settings: Settings, capsys: pytest.CaptureFixture[str]) -> Callable[[], list[dict[str, Any]]]:
    """Configure logging as the app does (JSON, because ``settings.env`` is ``test``) and return a function
    that gives the JSON log lines written to stderr since it was last called."""
    configure_logging(settings)

    def read() -> list[dict[str, Any]]:
        lines = capsys.readouterr().err.splitlines()
        return [json.loads(line) for line in lines if line.startswith("{")]

    return read


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Test settings: ``env=test``, no .env file, all storage under tmp_path."""
    return Settings(
        env="test",
        db_url=f"sqlite:///{(tmp_path / 'gtm_studio.db').as_posix()}",
        storage_dir=tmp_path / "storage",
    )


@pytest.fixture
def api_routes(settings: Settings) -> list[RouteInfo]:
    """Every endpoint of the app. Use it for any test that audits all routes."""
    return list_routes(create_app(settings))


@pytest.fixture
def migrated_engine(settings: Settings) -> Iterator[Engine]:
    """An engine on a fresh database (in tmp_path, so one per test) migrated to head by Alembic."""
    upgrade(settings)
    engine = make_engine(settings)
    try:
        yield engine
    finally:
        engine.dispose()  # releases the SQLite file so tmp_path can be cleaned up on Windows


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session on the migrated test database. It does not commit for you."""
    with make_session_factory(migrated_engine)() as session:
        yield session


@pytest.fixture
def client(settings: Settings, migrated_engine: Engine) -> Iterator[TestClient]:
    """A TestClient for an app built from the test settings, on the migrated database. Entering it
    runs the app lifespan."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def uow_factory(migrated_engine: Engine) -> UnitOfWorkFactory:
    """Units of work on the migrated test database, as services receive them."""
    return partial(SqlUnitOfWork, make_session_factory(migrated_engine))


@pytest.fixture
def seeded(uow_factory: UnitOfWorkFactory) -> SeedSummary:
    """The migrated database with the demo users from ``config/dev_users.yaml`` in it."""
    return IdentityService(uow_factory).seed_dev_users(REPO_ROOT / "config" / "dev_users.yaml")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """An app built from the test settings. Add test-only routes to it before using ``login_as``."""
    return create_app(settings)


LoginAs = Callable[..., TestClient]


@pytest.fixture
def login_as(app: FastAPI, seeded: SeedSummary) -> Iterator[LoginAs]:
    """``login_as("pmm")``: a TestClient signed in as the first seeded user holding that role. Each call
    gets its own cookie jar, so one test can act as several people. Pass ``csrf=False`` to leave out the
    ``X-Requested-With`` header on every request after the login."""
    with TestClient(app):  # runs the lifespan once, for every client below

        def _login_as(role_key: str, *, csrf: bool = True) -> TestClient:
            http = TestClient(app)
            header = {"X-Requested-With": "gtm-studio"}
            users = http.get("/api/auth/options").json()["dev_users"]
            user = next(u for u in users if role_key in u["roles"])
            response = http.post("/api/auth/dev/login", json={"user_id": user["id"]}, headers=header)
            assert response.status_code == 200, response.text
            if csrf:
                http.headers.update(header)
            return http

        yield _login_as
