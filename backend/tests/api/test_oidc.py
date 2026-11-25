"""OIDC sign-in, end to end through the real routes with no network.

``FakeIdp`` stands in for the identity provider: it publishes metadata and a signing key and turns the
browser's ``code`` into a token response with a really signed ID token. Everything after that is authlib's
own validation (state, PKCE, signature, ``iss``, ``aud``, ``exp``, nonce), so these tests also prove the
app wires it up right. Only two authlib methods are replaced: the ones that would touch the network.
"""

import base64
import hashlib
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from authlib.integrations.starlette_client import StarletteOAuth2App
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey
from pydantic import SecretStr, ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from structlog.testing import capture_logs

from gtm_studio.api.app import create_app
from gtm_studio.auth.oidc import RoleMapError
from gtm_studio.db.models.identity import Role
from gtm_studio.domain.audit import AuditAction, AuditEventView, AuditFilters
from gtm_studio.services.identity import SeedSummary
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import Settings

FRONTEND = "http://localhost:5173"  # the default frontend_base_url


class FakeIdp:
    def __init__(self, issuer: str, client_id: str) -> None:
        self.issuer = issuer
        self.client_id = client_id
        self.key = RSAKey.generate_key(2048, parameters={"kid": "k1", "use": "sig"})
        self.signing_key = self.key  # swap for another key to forge a signature
        self.claims: dict[str, Any] = {
            "sub": "sub-1",
            "email": "ada@example.test",
            "name": "Ada",
            "groups": ["pmm-group"],
        }
        self.token_overrides: dict[str, Any] = {}  # replaces claims in the ID token; None removes one
        self.omit_id_token = False
        self.unreachable = False
        self.authorize: dict[str, str] = {}  # the query of the last authorization request
        self.exchanges: list[dict[str, Any]] = []  # what the app sent to the token endpoint

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "jwks": {"keys": [self.key.as_dict(private=False)]},
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    def id_token(self) -> str:
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "aud": self.client_id,
            "iat": now,
            "exp": now + 300,
            "nonce": self.authorize["nonce"],  # the IdP echoes the nonce it was given
            **self.claims,
            **self.token_overrides,
        }
        payload = {name: value for name, value in claims.items() if value is not None}
        return jwt.encode({"alg": "RS256", "kid": "k1"}, payload, self.signing_key)

    def start(self, browser: TestClient, **params: str) -> str:
        """The browser asks the app to sign in and is sent to the IdP. Returns the ``state``."""
        response = browser.get("/api/auth/oidc/login", params=params, follow_redirects=False)
        assert response.status_code == 302, response.text
        location = urlsplit(response.headers["location"])
        assert f"{location.scheme}://{location.netloc}{location.path}" == f"{self.issuer}/authorize"
        self.authorize = {name: values[0] for name, values in parse_qs(location.query).items()}
        return self.authorize["state"]

    def call_back(self, browser: TestClient, state: str, **params: str) -> Any:
        query = {"code": "the-code", "state": state, **params}
        return browser.get("/api/auth/oidc/callback", params=query, follow_redirects=False)

    def sign_in(self, browser: TestClient, **params: str) -> Any:
        """The whole round trip. Returns the callback's response (a redirect)."""
        return self.call_back(browser, self.start(browser, **params))


@pytest.fixture
def idp(oidc_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> FakeIdp:
    assert oidc_settings.oidc_issuer and oidc_settings.oidc_client_id
    fake = FakeIdp(oidc_settings.oidc_issuer, oidc_settings.oidc_client_id)

    async def load_server_metadata(self: object) -> dict[str, Any]:
        if fake.unreachable:
            raise httpx2.ConnectError("no route to the identity provider")
        return fake.metadata

    async def fetch_access_token(self: object, redirect_uri: str | None = None, **kwargs: Any) -> Any:
        fake.exchanges.append({"redirect_uri": redirect_uri, **kwargs})
        token: dict[str, Any] = {"access_token": "an-access-token", "token_type": "Bearer", "expires_in": 300}
        if not fake.omit_id_token:
            token["id_token"] = fake.id_token()
        return token

    monkeypatch.setattr(StarletteOAuth2App, "load_server_metadata", load_server_metadata)
    monkeypatch.setattr(StarletteOAuth2App, "fetch_access_token", fetch_access_token)
    return fake


@pytest.fixture
def browser(oidc_settings: Settings, seeded: SeedSummary, idp: FakeIdp) -> Iterator[TestClient]:
    """A browser talking to an app in OIDC mode. The dev seed stands in for a catalog that declares the
    approver roles (pmm, product, cs)."""
    with TestClient(create_app(oidc_settings)) as client:
        yield client


def _events(uow_factory: UnitOfWorkFactory) -> list[AuditEventView]:
    """Every audit event, oldest first, apart from the seeding's and the catalog's start-up role sync."""
    with uow_factory() as uow:
        items = reversed(uow.audit.query(AuditFilters(), None, 100).items)
    seeded = (AuditAction.USER_SEEDED, AuditAction.USER_ROLES_SET)
    return [e for e in items if e.action not in seeded and not e.action.startswith("catalog.")]


def _roles(browser: TestClient) -> list[str]:
    return browser.get("/api/auth/me").json()["roles"]


# ---------------------------------------------------------------- the flow


def test_login_sends_the_browser_to_the_idp_with_pkce_state_and_a_nonce(
    browser: TestClient, idp: FakeIdp, oidc_settings: Settings
) -> None:
    idp.start(browser)
    sent = idp.authorize
    assert sent["response_type"] == "code"
    assert sent["client_id"] == "gtm-studio"
    assert sent["redirect_uri"] == oidc_settings.oidc_redirect_url
    assert sent["scope"] == "openid email profile"
    assert sent["code_challenge_method"] == "S256"
    assert sent["state"] and sent["nonce"] and sent["code_challenge"]


def test_a_first_login_creates_the_user_with_the_mapped_roles(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    response = idp.sign_in(browser)
    assert response.status_code == 302
    assert response.headers["location"] == f"{FRONTEND}/"

    me = browser.get("/api/auth/me").json()
    assert (me["email"], me["display_name"], me["roles"]) == ("ada@example.test", "Ada", ["pmm"])
    assert "asset:review" in me["permissions"]
    with uow_factory() as uow:
        user = uow.identity.get_user_by_subject("oidc", "sub-1")
    assert user is not None
    assert (user.auth_provider, user.is_active, user.last_login_at is not None) == ("oidc", True, True)

    provisioned, synced, login = _events(uow_factory)
    assert provisioned.action == "user.provisioned"
    assert (synced.action, synced.details) == (
        "user.roles_synced",
        {"source": "oidc", "added": ["pmm"], "removed": []},
    )
    assert (login.action, login.actor_user_id, login.entity_id) == ("auth.login", user.id, user.id)
    assert login.details == {"provider": "oidc", "roles_synced": ["pmm"]}


def test_the_code_is_exchanged_with_the_pkce_verifier_and_the_registered_redirect(
    browser: TestClient, idp: FakeIdp, oidc_settings: Settings
) -> None:
    idp.sign_in(browser)
    [exchange] = idp.exchanges
    assert exchange["code"] == "the-code"
    assert exchange["redirect_uri"] == oidc_settings.oidc_redirect_url
    digest = hashlib.sha256(exchange["code_verifier"].encode("ascii")).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == idp.authorize["code_challenge"]


def test_a_second_login_updates_the_oidc_grants_and_keeps_the_manual_ones(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    idp.sign_in(browser)
    with uow_factory() as uow:  # an admin gives the user `cs` by hand
        user = uow.identity.get_user_by_subject("oidc", "sub-1")
        assert user is not None
        uow.identity.sync_source_roles(user.id, ["cs"], source="dev_seed")
    assert _roles(browser) == ["cs", "pmm"]

    idp.claims["groups"] = ["product-group"]
    idp.sign_in(browser)
    assert _roles(browser) == ["cs", "product"]  # pmm is gone, cs stays
    synced = _events(uow_factory)[-2]
    assert (synced.action, synced.details) == (
        "user.roles_synced",
        {"source": "oidc", "added": ["product"], "removed": ["pmm"]},
    )

    idp.claims["groups"] = []  # in no mapped group any more: the default roles
    idp.sign_in(browser)
    assert _roles(browser) == ["cs", "viewer"]


def test_the_profile_follows_the_idp(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    idp.sign_in(browser)
    idp.claims |= {"name": "Ada Lovelace", "email": "Ada.Lovelace@Example.test"}
    idp.sign_in(browser)
    me = browser.get("/api/auth/me").json()
    assert (me["display_name"], me["email"]) == ("Ada Lovelace", "ada.lovelace@example.test")
    updated = next(e for e in _events(uow_factory) if e.action == "user.updated")
    assert updated.details == {"provider": "oidc", "fields": ["email", "display_name"]}
    assert updated.before_hash and updated.after_hash and updated.before_hash != updated.after_hash


def test_a_group_claim_may_be_one_string_and_the_groups_of_one_person_add_up(
    browser: TestClient, idp: FakeIdp
) -> None:
    idp.claims["groups"] = "pmm-group"
    idp.sign_in(browser)
    assert _roles(browser) == ["pmm"]
    idp.claims["groups"] = ["pmm-group", "product-group", "unmapped"]
    idp.sign_in(browser)
    assert _roles(browser) == ["pmm", "product"]


def test_an_id_token_without_groups_gets_the_default_roles_and_a_warning(
    browser: TestClient, idp: FakeIdp
) -> None:
    del idp.claims["groups"]
    idp.claims["_claim_names"] = {"groups": "src1"}  # Entra ID's "overage": too many groups to list
    with capture_logs() as logs:
        idp.sign_in(browser)
    assert _roles(browser) == ["viewer"]
    [warning] = [e for e in logs if e["event"].startswith("the ID token has no groups")]
    assert warning["overage"] is True


def test_the_sign_in_name_stands_in_for_a_missing_email(browser: TestClient, idp: FakeIdp) -> None:
    del idp.claims["email"]
    idp.claims["preferred_username"] = "Ada.Lovelace@Example.test"
    idp.sign_in(browser)
    assert browser.get("/api/auth/me").json()["email"] == "ada.lovelace@example.test"


# ---------------------------------------------------------------- refusals that are audited


def test_an_inactive_user_is_denied_and_audited_and_keeps_their_roles(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    idp.sign_in(browser)
    with uow_factory() as uow:
        user = uow.identity.get_user_by_subject("oidc", "sub-1")
        assert user is not None
        uow.identity.upsert_user(replace(user, is_active=False))
    browser.cookies.clear()
    idp.claims["groups"] = ["admins"]  # would make them an admin if the sign-in got that far

    response = idp.sign_in(browser)
    assert response.headers["location"] == f"{FRONTEND}/login?error=denied"
    assert browser.get("/api/auth/me").status_code == 401
    denied = _events(uow_factory)[-1]
    assert (denied.action, denied.actor_user_id, denied.actor_display) == (
        "auth.login_denied",
        None,
        "system",
    )
    assert (denied.entity_type, denied.entity_id) == ("user", user.id)
    assert denied.details == {"provider": "oidc", "reason": "inactive"}
    with uow_factory() as uow:
        stored = uow.identity.get_user(user.id)
    assert stored is not None
    assert stored.roles == {"pmm"}  # not re-synced


def test_an_email_that_belongs_to_another_user_is_refused_not_linked(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    idp.claims["email"] = "avery.admin@example.test"  # a seeded user's address
    response = idp.sign_in(browser)
    assert response.headers["location"] == f"{FRONTEND}/login?error=denied"
    assert browser.get("/api/auth/me").status_code == 401
    [denied] = _events(uow_factory)  # nothing was provisioned either
    assert (denied.action, denied.entity_id) == ("auth.login_denied", "sub-1")
    assert denied.details == {"provider": "oidc", "reason": "email_conflict"}
    with uow_factory() as uow:
        assert uow.identity.get_user_by_subject("oidc", "sub-1") is None


def test_an_id_token_with_no_usable_email_is_denied(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    del idp.claims["email"]
    idp.claims["preferred_username"] = "ada"  # not an address
    assert idp.sign_in(browser).headers["location"] == f"{FRONTEND}/login?error=denied"
    [denied] = _events(uow_factory)
    assert denied.details["reason"] == "no_email"


# ---------------------------------------------------------------- the redirect target


@pytest.mark.parametrize(
    "hostile",
    [
        "https://evil.example",
        "//evil.example",
        "/\\evil.example",
        "/\t/evil.example",
        "evil",
        "/" + "a" * 600,
    ],
)
def test_an_unsafe_next_falls_back_to_the_home_page(browser: TestClient, idp: FakeIdp, hostile: str) -> None:
    response = idp.sign_in(browser, next=hostile)
    assert response.status_code == 302
    assert response.headers["location"] == f"{FRONTEND}/"
    assert browser.get("/api/auth/me").status_code == 200  # signed in; only the target was dropped


def test_a_same_site_next_is_kept_once(browser: TestClient, idp: FakeIdp) -> None:
    response = idp.sign_in(browser, next="/activity?action_prefix=auth.")
    assert response.headers["location"] == f"{FRONTEND}/activity?action_prefix=auth."
    assert idp.sign_in(browser).headers["location"] == f"{FRONTEND}/"  # not remembered for the next login


# ---------------------------------------------------------------- flows that must sign nobody in


def _assert_refused(browser: TestClient, response: Any, uow_factory: UnitOfWorkFactory) -> None:
    assert response.status_code == 302
    assert response.headers["location"] == f"{FRONTEND}/login?error=failed"
    assert browser.get("/api/auth/me").status_code == 401
    # Not audited: nobody was identified, the endpoint is open, and audit rows can't be deleted.
    assert _events(uow_factory) == []
    with uow_factory() as uow:
        assert uow.identity.get_user_by_subject("oidc", "sub-1") is None


def test_a_callback_nobody_started_is_refused(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    response = idp.call_back(browser, state="made-up")
    _assert_refused(browser, response, uow_factory)
    assert idp.exchanges == []  # the code was never sent anywhere


def test_a_state_from_another_browser_is_refused(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    """Login CSRF: an attacker starts a flow, then tricks a victim's browser into finishing it."""
    state = idp.start(TestClient(browser.app))  # the attacker's own browser, with its own cookie
    _assert_refused(browser, idp.call_back(browser, state), uow_factory)


def test_a_state_cannot_be_used_twice(browser: TestClient, idp: FakeIdp) -> None:
    state = idp.start(browser)
    assert idp.call_back(browser, state).headers["location"] == f"{FRONTEND}/"
    assert idp.call_back(browser, state).headers["location"] == f"{FRONTEND}/login?error=failed"
    assert len(idp.exchanges) == 1


def test_an_error_from_the_idp_signs_nobody_in(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    state = idp.start(browser)
    response = idp.call_back(browser, state, error="access_denied", error_description="the user said no")
    _assert_refused(browser, response, uow_factory)


@pytest.mark.parametrize(
    "override",
    [
        {"aud": "another-app"},
        {"iss": "https://evil.example"},
        {"nonce": "not-the-one-we-sent"},
        {"nonce": None},
        {"exp": 1},
        {"sub": None},
    ],
    ids=["audience", "issuer", "nonce", "no-nonce", "expired", "no-subject"],
)
def test_an_id_token_that_does_not_validate_signs_nobody_in(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory, override: dict[str, Any]
) -> None:
    idp.token_overrides = override
    _assert_refused(browser, idp.sign_in(browser), uow_factory)


def test_an_id_token_signed_with_another_key_signs_nobody_in(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    idp.signing_key = RSAKey.generate_key(2048, parameters={"kid": "k1", "use": "sig"})
    _assert_refused(browser, idp.sign_in(browser), uow_factory)


def test_a_token_response_without_an_id_token_signs_nobody_in(
    browser: TestClient, idp: FakeIdp, uow_factory: UnitOfWorkFactory
) -> None:
    idp.omit_id_token = True
    with capture_logs() as logs:
        response = idp.sign_in(browser)
    _assert_refused(browser, response, uow_factory)
    assert any(e.get("reason") == "no_id_token" for e in logs)


def test_an_unreachable_idp_is_a_bad_gateway_and_the_flow_never_starts(
    browser: TestClient, idp: FakeIdp
) -> None:
    idp.unreachable = True
    assert browser.get("/api/auth/oidc/login", follow_redirects=False).status_code == 502


# ---------------------------------------------------------------- roles nobody declares yet


def test_a_mapped_role_nothing_declares_is_created_inactive_and_grants_nothing(
    oidc_settings: Settings, idp: FakeIdp, db_session: Session
) -> None:
    oidc_settings.oidc_role_map_file.write_text("group_to_roles: {pmm-group: [growth]}\n", encoding="utf-8")
    with TestClient(create_app(oidc_settings)) as browser, capture_logs() as logs:
        idp.sign_in(browser)
        me = browser.get("/api/auth/me").json()
    assert (me["roles"], me["permissions"]) == ([], [])
    role = db_session.get(Role, "growth")
    assert role is not None
    assert (role.active, role.source) == (False, "oidc")
    assert any(e["event"].startswith("created an inactive role") and e["role"] == "growth" for e in logs)


# ---------------------------------------------------------------- the provider switch and settings


def test_the_oidc_routes_are_404_unless_the_provider_is_oidc(client: TestClient) -> None:
    assert client.get("/api/auth/oidc/login", follow_redirects=False).status_code == 404
    assert client.get("/api/auth/oidc/callback", follow_redirects=False).status_code == 404


def test_oidc_mode_needs_nothing_but_settings_and_a_role_map(browser: TestClient) -> None:
    """Every test above runs the real app in OIDC mode from `Settings` and a role-map file alone. Here:
    the login page is told, and the dev login is closed."""
    assert browser.get("/api/auth/options").json() == {"provider": "oidc", "dev_users": []}
    csrf = {"X-Requested-With": "gtm-studio"}
    assert browser.post("/api/auth/dev/login", json={"user_id": "x"}, headers=csrf).status_code == 404


def test_a_missing_role_map_stops_the_app_at_start_up(
    oidc_settings: Settings, migrated_engine: Engine
) -> None:
    oidc_settings.oidc_role_map_file.unlink()
    with pytest.raises(RoleMapError, match=r"oidc_roles\.yaml"), TestClient(create_app(oidc_settings)):
        pass


OIDC_VALUES: dict[str, Any] = {
    "oidc_issuer": "https://idp.example.test",
    "oidc_client_id": "gtm-studio",
    "oidc_client_secret": SecretStr("client-secret-value"),
    "oidc_redirect_url": "https://gtm.example.test/api/auth/oidc/callback",
}


@pytest.mark.parametrize("missing", list(OIDC_VALUES))
def test_settings_refuse_oidc_with_a_missing_value(missing: str) -> None:
    values = {name: value for name, value in OIDC_VALUES.items() if name != missing}
    with pytest.raises(ValidationError, match=f"GTM_{missing.upper()}"):
        Settings(auth_provider="oidc", **values)


@pytest.mark.parametrize(
    ("name", "blank"),
    [("oidc_issuer", "  "), ("oidc_client_id", "  "), ("oidc_client_secret", SecretStr(" "))],
)
def test_a_blank_value_counts_as_missing_and_the_dev_provider_needs_none(name: str, blank: object) -> None:
    with pytest.raises(ValidationError, match=f"GTM_{name.upper()}"):
        Settings(auth_provider="oidc", **{**OIDC_VALUES, name: blank})
    assert Settings(auth_provider="dev").oidc_issuer is None


def test_urls_are_checked_and_lose_a_trailing_slash() -> None:
    assert Settings(
        auth_provider="oidc", **{**OIDC_VALUES, "oidc_issuer": "https://idp.example.test/"}
    ).oidc_issuer == ("https://idp.example.test")
    with pytest.raises(ValidationError, match="http"):
        Settings(auth_provider="oidc", **{**OIDC_VALUES, "oidc_issuer": "idp.example.test"})


def test_the_role_map_is_found_in_the_config_dir_unless_a_path_is_given(tmp_path: Path) -> None:
    assert Settings(config_dir=tmp_path).oidc_role_map_file == tmp_path / "oidc_roles.yaml"
    elsewhere = tmp_path / "elsewhere.yaml"
    assert Settings(config_dir=tmp_path, oidc_role_map_path=elsewhere).oidc_role_map_file == elsewhere


@pytest.mark.parametrize("name", ["oidc_issuer", "oidc_redirect_url", "frontend_base_url"])
def test_production_needs_https_for_every_url(name: str) -> None:
    hosted: dict[str, Any] = {
        **OIDC_VALUES,
        "frontend_base_url": "https://gtm.example.test",
        "session_secret": SecretStr("s" * 48),
    }
    assert Settings(env="production", auth_provider="oidc", **hosted).env == "production"
    with pytest.raises(ValidationError, match=f"{name} must be an https URL"):
        Settings(env="production", auth_provider="oidc", **{**hosted, name: "http://plain.example.test"})
