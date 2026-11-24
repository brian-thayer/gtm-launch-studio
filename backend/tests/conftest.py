"""Shared fixtures. Tests never read the developer's real backend/.env or GTM_* environment."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gtm_studio.api.app import create_app
from gtm_studio.api.introspection import RouteInfo, list_routes
from gtm_studio.settings import Settings


@pytest.fixture(autouse=True)
def _isolate_settings_from_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's shell and backend/.env out of every test.

    Removes the GTM_* variables and turns off the .env file at the class level. (Not ``_env_file=None``
    per call: pyright drops pydantic-settings' underscore keyword arguments.)
    """
    for name in [n for n in os.environ if n.startswith("GTM_")]:
        monkeypatch.delenv(name)
    monkeypatch.setitem(Settings.model_config, "env_file", None)


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
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient for an app built from the test settings. Entering it runs the app lifespan."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client
