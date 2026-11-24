import pytest
from fastapi.testclient import TestClient

from gtm_studio.api.app import create_app
from gtm_studio.api.introspection import RouteInfo
from gtm_studio.settings import Settings


def test_create_app_stores_the_settings_it_was_given(settings: Settings) -> None:
    app = create_app(settings)
    assert app.state.settings is settings


def test_create_app_builds_settings_when_none_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "test")
    assert create_app().state.settings.env == "test"


def test_route_enumeration_sees_included_routers(api_routes: list[RouteInfo]) -> None:
    health = [r for r in api_routes if r.path == "/api/health"]
    assert len(health) == 1
    assert health[0].methods == {"GET"}
    assert health[0].route is not None


def test_every_route_is_under_the_api_prefix(api_routes: list[RouteInfo]) -> None:
    """The dev proxy only forwards /api, so a route outside it would be unreachable from the frontend."""
    assert api_routes
    assert [r.path for r in api_routes if not r.path.startswith("/api/")] == []


def test_every_api_route_declares_a_response_model_and_a_tag(api_routes: list[RouteInfo]) -> None:
    routes = [r.route for r in api_routes if r.route is not None]
    assert routes
    assert [r.path for r in routes if r.response_model is None and r.status_code != 204] == []
    assert [r.path for r in routes if not r.tags] == []


def test_interactive_docs_are_available_outside_production(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200


def test_interactive_docs_are_off_in_production(settings: Settings) -> None:
    prod = settings.model_copy(update={"env": "production"})
    with TestClient(create_app(prod)) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404
        assert client.get("/api/health").status_code == 200
