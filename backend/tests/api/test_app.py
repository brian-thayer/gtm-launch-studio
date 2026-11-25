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
    # 204 and 302 have no body to describe (the OIDC login and callback redirect the browser).
    assert [r.path for r in routes if r.response_model is None and r.status_code not in (204, 302)] == []
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


_ORIGIN = "http://localhost:5173"
_PREFLIGHT = {
    "Origin": _ORIGIN,
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "x-requested-with",
}


def test_cors_is_off_by_default(client: TestClient) -> None:
    response = client.options("/api/health", headers=_PREFLIGHT)
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": _ORIGIN}).headers


def test_cors_allows_only_the_configured_origins(settings: Settings) -> None:
    cors = settings.model_copy(update={"cors_origins": [_ORIGIN]})
    with TestClient(create_app(cors)) as client:
        preflight = client.options("/api/health", headers=_PREFLIGHT)
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == _ORIGIN
        assert preflight.headers["access-control-allow-credentials"] == "true"
        assert "x-requested-with" in preflight.headers["access-control-allow-headers"].lower()

        other = client.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in other.headers


def test_cors_does_not_change_the_openapi_schema(settings: Settings) -> None:
    """The schema never depends on settings: middleware must not add routes or parameters."""
    cors = settings.model_copy(update={"cors_origins": [_ORIGIN]})
    assert create_app(cors).openapi() == create_app(settings).openapi()
