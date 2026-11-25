from collections.abc import Callable
from dataclasses import replace
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from structlog.testing import capture_logs

from gtm_studio.api.app import create_app
from gtm_studio.api.introspection import RouteInfo, list_routes
from gtm_studio.api.schemas.auth import Me
from gtm_studio.auth.deps import current_actor, require
from gtm_studio.auth.session import SESSION_COOKIE, SESSION_MAX_AGE, session_user_id, start_session
from gtm_studio.domain.identity import Actor, Permission
from gtm_studio.services.identity import SeedSummary
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import DEV_SESSION_SECRET, Settings

CSRF = {"X-Requested-With": "gtm-studio"}
PMM_ID = "00000000-0000-4000-8000-000000000003"
GOOD_SECRET = "s" * 48

# ------------------------------------------------------------------ the route guard (stays forever)

# Open because they are how a session starts (or, for health and options, what a signed-out page needs).
# The OIDC pair change nothing until the identity provider has vouched for someone (tests/api/test_oidc.py).
OPEN_ROUTES = {
    "/api/health",
    "/api/auth/options",
    "/api/auth/dev/login",
    "/api/auth/oidc/login",
    "/api/auth/oidc/callback",
}


def _requires_a_session(dependant: Dependant) -> bool:
    return any(d.call is current_actor or _requires_a_session(d) for d in dependant.dependencies)


def test_every_route_but_the_open_ones_needs_a_session(api_routes: list[RouteInfo]) -> None:
    """The guard: a new endpoint that forgets `current_actor` / `require(...)` fails here. Routes with no
    APIRoute are the plain Starlette interactive docs, which are exempt."""
    # Pairs, not a dict: one path can have several routes (GET and POST), and each must be checked.
    api = [(r.path, r.route) for r in api_routes if r.route is not None]
    assert {path for path, _ in api} >= OPEN_ROUTES  # the allowlist can't silently go stale
    unprotected = [
        f"{sorted(route.methods or [])} {path}"
        for path, route in api
        if path not in OPEN_ROUTES and not _requires_a_session(route.dependant)
    ]
    assert unprotected == []


def test_the_guard_notices_an_unprotected_route(settings: Settings) -> None:
    app = create_app(settings)
    router = APIRouter(prefix="/api/_probe", tags=["probe"])

    @router.get("/open")
    def open_route() -> dict[str, str]:
        return {}

    @router.get("/closed")
    def closed_route(_: Annotated[Actor, Depends(require(Permission.SOLUTION_READ))]) -> dict[str, str]:
        return {}

    app.include_router(router)
    found = {r.path: r.route for r in list_routes(app) if r.route is not None}
    assert not _requires_a_session(found["/api/_probe/open"].dependant)
    assert _requires_a_session(found["/api/_probe/closed"].dependant)


# ------------------------------------------------------------------ login, me, logout


def test_options_lists_the_seeded_users_without_a_session(client: TestClient, seeded: SeedSummary) -> None:
    body = client.get("/api/auth/options").json()
    assert body["provider"] == "dev"
    users = {u["display_name"]: u for u in body["dev_users"]}
    assert len(users) == 5
    assert users["Avery Admin"]["roles"] == ["admin"]
    assert set(users["Avery Admin"]) == {"id", "display_name", "roles"}  # no email, no flags


def test_login_me_and_logout(client: TestClient, seeded: SeedSummary) -> None:
    assert client.get("/api/auth/me").status_code == 401

    login = client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
    assert login.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == login.json()
    assert me.json() == {
        "id": PMM_ID,
        "email": "priya.pmm@example.test",
        "display_name": "Priya Marketing",
        "roles": ["pmm"],
        "permissions": [
            "asset:generate",
            "asset:review",
            "catalog:read",
            "context:write",
            "import:run",
            "solution:read",
        ],
    }

    assert client.post("/api/auth/logout", headers=CSRF).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_records_the_login_time(
    client: TestClient, seeded: SeedSummary, uow_factory: UnitOfWorkFactory
) -> None:
    client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
    with uow_factory() as uow:
        user = uow.identity.get_user(PMM_ID)
    assert user is not None
    assert user.last_login_at is not None


def test_logging_in_as_someone_else_replaces_the_session(client: TestClient, seeded: SeedSummary) -> None:
    client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
    options = client.get("/api/auth/options").json()["dev_users"]
    admin = next(u for u in options if u["roles"] == ["admin"])
    client.post("/api/auth/dev/login", json={"user_id": admin["id"]}, headers=CSRF)
    assert client.get("/api/auth/me").json()["roles"] == ["admin"]


def test_login_as_an_unknown_user_is_404(client: TestClient, seeded: SeedSummary) -> None:
    response = client.post(
        "/api/auth/dev/login", json={"user_id": "99999999-9999-4999-8999-999999999999"}, headers=CSRF
    )
    assert response.status_code == 404
    assert client.get("/api/auth/me").status_code == 401


def test_login_rejects_an_oversized_user_id(client: TestClient, seeded: SeedSummary) -> None:
    response = client.post("/api/auth/dev/login", json={"user_id": "x" * 37}, headers=CSRF)
    assert response.status_code == 422


def test_login_as_an_inactive_user_is_404(
    client: TestClient, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    _deactivate(uow_factory, PMM_ID)
    assert client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF).status_code == 404
    assert PMM_ID not in {u["id"] for u in client.get("/api/auth/options").json()["dev_users"]}


def test_a_session_ends_when_its_user_is_deactivated(
    client: TestClient, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
    assert client.get("/api/auth/me").status_code == 200
    _deactivate(uow_factory, PMM_ID)
    assert client.get("/api/auth/me").status_code == 401


def _deactivate(uow_factory: UnitOfWorkFactory, user_id: str) -> None:
    with uow_factory() as uow:
        record = uow.identity.get_user(user_id)
        assert record is not None
        uow.identity.upsert_user(replace(record, is_active=False))


def test_a_tampered_session_cookie_is_ignored(client: TestClient, seeded: SeedSummary) -> None:
    client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
    valid = client.cookies[SESSION_COOKIE]
    client.cookies.clear()  # `cookies.set` alone would send the valid cookie too (another domain)
    client.cookies.set(SESSION_COOKIE, valid + "x")
    assert client.get("/api/auth/me").status_code == 401


def test_a_cookie_signed_with_another_secret_is_ignored(
    settings: Settings, client: TestClient, seeded: SeedSummary
) -> None:
    other = settings.model_copy(update={"session_secret": SecretStr("another-secret-another-secret-xx")})
    with TestClient(create_app(other)) as elsewhere:
        elsewhere.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
        forged = elsewhere.cookies[SESSION_COOKIE]
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, forged)
    assert client.get("/api/auth/me").status_code == 401


# ------------------------------------------------------------------ the session cookie


def test_the_session_cookie_is_httponly_and_samesite_lax(client: TestClient, seeded: SeedSummary) -> None:
    response = client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert f"max-age={SESSION_MAX_AGE}" in cookie
    assert "secure" not in cookie  # outside production, so plain-http localhost works


def test_the_session_cookie_is_secure_in_production(settings: Settings, seeded: SeedSummary) -> None:
    # model_copy skips validation: the dev provider can't be configured in production, but it lets us
    # look at the cookie the middleware would set there.
    prod = settings.model_copy(update={"env": "production"})
    with TestClient(create_app(prod), base_url="https://testserver") as https_client:
        response = https_client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_session_helpers_expire_old_and_malformed_sessions() -> None:
    session: dict[str, object] = {}
    start_session(session, "u1", now=1000)
    assert session_user_id(session, now=1000 + SESSION_MAX_AGE) == "u1"
    assert session_user_id(session, now=1000 + SESSION_MAX_AGE + 1) is None
    assert session_user_id({}) is None
    assert session_user_id({"user_id": "u1"}) is None  # no issued_at
    assert session_user_id({"user_id": 7, "issued_at": 1000}, now=1000) is None


# ------------------------------------------------------------------ permissions


def test_require_gives_403_when_the_permission_is_missing(
    app: FastAPI, login_as: Callable[..., TestClient]
) -> None:
    router = APIRouter(prefix="/api/_probe", tags=["probe"])

    @router.get("/audit", response_model=Me)
    def audit(actor: Annotated[Actor, Depends(require(Permission.AUDIT_READ))]) -> Me:
        return Me.from_actor(actor)

    app.include_router(router)

    assert login_as("viewer").get("/api/_probe/audit").status_code == 403
    assert login_as("pmm").get("/api/_probe/audit").status_code == 403
    admin = login_as("admin")
    assert admin.get("/api/_probe/audit").status_code == 200
    anonymous = TestClient(app)
    assert anonymous.get("/api/_probe/audit").status_code == 401  # no session beats no permission


def test_login_as_gives_each_call_its_own_session(login_as: Callable[..., TestClient]) -> None:
    viewer, pmm = login_as("viewer"), login_as("pmm")
    assert viewer.get("/api/auth/me").json()["roles"] == ["viewer"]
    assert pmm.get("/api/auth/me").json()["roles"] == ["pmm"]
    assert viewer.get("/api/auth/me").json()["roles"] == ["viewer"]


# ------------------------------------------------------------------ CSRF


def test_state_changing_requests_need_the_csrf_header(client: TestClient, seeded: SeedSummary) -> None:
    for method, path in [
        ("POST", "/api/auth/dev/login"),
        ("POST", "/api/auth/logout"),
        ("PUT", "/api/anything"),
        ("PATCH", "/api/anything"),
        ("DELETE", "/api/anything"),
    ]:
        response = client.request(method, path)
        assert response.status_code == 403, (method, path)
        assert response.json() == {"detail": "missing CSRF header"}


def test_the_csrf_header_must_have_the_right_value(client: TestClient, seeded: SeedSummary) -> None:
    response = client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers={"X-Requested-With": "x"})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_reads_do_not_need_the_csrf_header(client: TestClient, seeded: SeedSummary) -> None:
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/options").status_code == 200
    assert client.get("/api/auth/me").status_code == 401  # not 403


def test_a_login_without_the_csrf_header_does_not_sign_in(client: TestClient, seeded: SeedSummary) -> None:
    client.post("/api/auth/dev/login", json={"user_id": PMM_ID})
    assert client.get("/api/auth/me").status_code == 401


# ------------------------------------------------------------------ the provider switch


def test_dev_login_is_disabled_when_the_provider_is_oidc(
    oidc_settings: Settings, seeded: SeedSummary
) -> None:
    with TestClient(create_app(oidc_settings)) as client:
        response = client.post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF)
        assert response.status_code == 404
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/auth/options").json() == {"provider": "oidc", "dev_users": []}


def test_the_openapi_schema_does_not_depend_on_the_provider(
    settings: Settings, oidc_settings: Settings
) -> None:
    assert create_app(oidc_settings).openapi() == create_app(settings).openapi()


# ------------------------------------------------------------------ settings


def test_production_refuses_the_dev_provider() -> None:
    with pytest.raises(ValidationError, match="auth_provider"):
        Settings(env="production", auth_provider="dev", session_secret=SecretStr(GOOD_SECRET))


def test_production_refuses_the_built_in_session_secret() -> None:
    with pytest.raises(ValidationError, match="session_secret"):
        Settings(env="production", auth_provider="oidc")
    with pytest.raises(ValidationError, match="session_secret"):
        Settings(env="production", auth_provider="oidc", session_secret=SecretStr(DEV_SESSION_SECRET))


def test_production_refuses_a_short_session_secret() -> None:
    with pytest.raises(ValidationError, match="at least"):
        Settings(env="production", auth_provider="oidc", session_secret=SecretStr("short"))


@pytest.mark.usefixtures("hosted_env")
def test_production_accepts_oidc_with_a_real_secret() -> None:
    s = Settings(env="production")
    assert (s.env, s.auth_provider) == ("production", "oidc")


def test_the_defaults_are_the_dev_provider_and_the_public_secret() -> None:
    s = Settings()
    assert (s.env, s.auth_provider) == ("dev", "dev")
    assert s.session_secret.get_secret_value() == DEV_SESSION_SECRET
    defaults = Settings.defaults()  # model_construct: no validation, always env=dev
    assert (defaults.env, defaults.auth_provider) == ("dev", "dev")


@pytest.mark.usefixtures("hosted_env")
def test_production_is_refused_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "production")
    monkeypatch.setenv("GTM_AUTH_PROVIDER", "dev")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("GTM_AUTH_PROVIDER", "oidc")
    assert Settings().env == "production"


@pytest.mark.usefixtures("hosted_env")
def test_secrets_are_not_shown_in_a_repr() -> None:
    s = Settings(env="production", session_secret=SecretStr(GOOD_SECRET))
    assert s.oidc_client_secret is not None
    for secret in (GOOD_SECRET, s.oidc_client_secret.get_secret_value()):
        assert secret not in repr(s)
        assert secret not in str(s)


def test_the_built_in_secret_logs_a_warning_when_serving_in_dev(settings: Settings) -> None:
    def warnings_for(s: Settings) -> list[str]:
        with capture_logs() as logs, TestClient(create_app(s)):
            pass
        return [e["event"] for e in logs if e["log_level"] == "warning"]

    dev = settings.model_copy(update={"env": "dev"})
    assert any("session secret" in e for e in warnings_for(dev))
    assert warnings_for(dev.model_copy(update={"session_secret": SecretStr(GOOD_SECRET)})) == []
    assert warnings_for(settings) == []  # env=test is quiet
