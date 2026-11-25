"""Sign in through an OpenID Connect identity provider (ADR-0002): Entra ID, Okta or any standards-compliant
IdP, by configuration alone (``GTM_OIDC_*`` and ``config/oidc_roles.yaml``).

The flow is the authorization-code flow with PKCE. authlib does the protocol work: ``state``, the nonce and
the PKCE verifier live in the signed session cookie, and the ID token's signature, ``iss``, ``aud``, ``exp``
and nonce are checked before this module sees a claim. What this module adds is policy: who the claims
describe, which roles their groups give, and refusing anyone who has been deactivated.

Like the dev provider, it never starts a session itself: the route does, once ``handle_callback`` returns.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
import structlog
import yaml
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import OAuth
from joserfc.errors import JoseError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse

from gtm_studio.domain.identity import ROLE_KEY, Actor, OidcRoleMap
from gtm_studio.services.identity import IdentityService, UserConflictError
from gtm_studio.settings import Settings

log = structlog.get_logger()

NEXT_KEY = "oidc_next"  # session key: where to send the person once they are signed in
MAX_NEXT_LENGTH = 512  # it travels in the session cookie, which browsers cap at about 4 KB
# These match the columns they end up in (db/models/identity.py, audit.py).
MAX_SUBJECT_LENGTH = 255
MAX_EMAIL_LENGTH = 320
MAX_NAME_LENGTH = 200
MAX_ENTITY_ID_LENGTH = 100

# What a call into authlib can raise when the IdP, the network or the token is at fault. Anything else is
# a bug in this code and is left to surface as a 500 (nobody is signed in either way).
_IDP_ERRORS = (AuthlibBaseError, JoseError, httpx2.HTTPError, ValueError, RuntimeError)


class OidcFlowError(Exception):
    """Sign-in failed before the IdP vouched for anyone: a bad or missing ``state``, a refused code, an ID
    token that doesn't validate. ``reason`` is a short code for the log. There is nobody to attribute it
    to, so it is logged, not audited: the callback is open to anyone and rows can't be deleted."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OidcDeniedError(OidcFlowError):
    """The IdP vouched for someone and we refuse them (deactivated, email owned by another user, no usable
    email). Audited as ``auth.login_denied``: only a real IdP account can cause one."""

    def __init__(self, reason: str, entity_id: str) -> None:
        super().__init__(reason)
        self.entity_id = entity_id[:MAX_ENTITY_ID_LENGTH]


class OidcUnavailableError(Exception):
    """The IdP could not be reached or its metadata is unusable."""


@dataclass(frozen=True)
class OidcSignIn:
    """A completed sign-in, ready for the route to start a session."""

    actor: Actor
    roles_synced: tuple[str, ...]  # what the IdP's groups mapped to (not the roles granted another way)
    next_path: str


# ---------------------------------------------------------------- the redirect target


def safe_next(value: object) -> str:
    """A same-site path to return to, or ``/``. Mirrors the frontend's ``safeNext``: a leading ``//`` or
    ``/\\`` is a protocol-relative URL, a scheme is another site, and browsers drop tabs and newlines from
    a URL (``/<tab>/host`` would become ``//host``), so control characters are refused too. Without this the
    sign-in would be an open redirect."""
    if not isinstance(value, str) or len(value) > MAX_NEXT_LENGTH:
        return "/"
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return "/"
    return value


# ---------------------------------------------------------------- the group -> role map


class RoleMapError(Exception):
    """``oidc_roles.yaml`` is missing or malformed. The message is meant for whoever deploys the app."""


class _RoleMapFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_to_roles: dict[str, list[str]] = Field(default_factory=dict)
    default_roles: list[str] = Field(default_factory=list)

    @field_validator("group_to_roles")
    @classmethod
    def _mapped_role_keys(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for group, roles in value.items():
            if not group.strip():
                raise ValueError("a group name is empty")
            _check_role_keys(roles)
        return value

    @field_validator("default_roles")
    @classmethod
    def _default_role_keys(cls, value: list[str]) -> list[str]:
        _check_role_keys(value)
        return value


def _check_role_keys(keys: list[str]) -> None:
    for key in keys:
        if not ROLE_KEY.fullmatch(key):
            raise ValueError(f"role key {key!r} must be lowercase letters, digits and underscores")


def load_role_map(path: Path) -> OidcRoleMap:
    """Read ``oidc_roles.yaml`` (see ``config/oidc_roles.example.yaml``). Raises ``RoleMapError``."""
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        parsed = _RoleMapFile.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise RoleMapError(f"{path}: {exc}") from exc
    return OidcRoleMap(
        group_to_roles={group: frozenset(roles) for group, roles in parsed.group_to_roles.items()},
        default_roles=frozenset(parsed.default_roles),
    )


# ---------------------------------------------------------------- the provider


class OidcAuthProvider:
    name = "oidc"

    def __init__(self, settings: Settings, role_map: OidcRoleMap, identity: IdentityService) -> None:
        issuer, client_id = settings.oidc_issuer, settings.oidc_client_id
        secret, redirect_url = settings.oidc_client_secret, settings.oidc_redirect_url
        if not (issuer and client_id and secret and redirect_url):
            raise ValueError("OIDC is not configured")  # Settings refuses this first
        oauth = OAuth()
        oauth.register(
            name="idp",
            client_id=client_id,
            client_secret=secret.get_secret_value(),
            # The IdP's endpoints and signing keys are fetched from here on first use, then kept.
            server_metadata_url=f"{issuer}/.well-known/openid-configuration",
            client_kwargs={"scope": settings.oidc_scopes, "code_challenge_method": "S256"},
        )
        self._client: Any = oauth.create_client("idp")
        self._redirect_url = redirect_url
        self._group_claim = settings.oidc_group_claim
        self._role_map = role_map
        self._identity = identity

    def login_options(self) -> dict[str, Any]:
        return {"provider": self.name}

    async def login_redirect(self, request: Request, next_path: str) -> RedirectResponse:
        """Send the browser to the IdP. ``state``, the nonce and the PKCE verifier are kept in the session;
        so is where to return to (checked now and again when it is used)."""
        try:
            response: RedirectResponse = await self._client.authorize_redirect(request, self._redirect_url)
        except _IDP_ERRORS as exc:
            log.warning("oidc login could not start", error=type(exc).__name__)
            raise OidcUnavailableError from exc
        request.session[NEXT_KEY] = safe_next(next_path)
        return response

    async def handle_callback(self, request: Request) -> OidcSignIn:
        """Finish a sign-in: exchange the code, validate the ID token, provision or update the user, sync
        their roles. Raises ``OidcDeniedError`` for a person we refuse and ``OidcFlowError`` for a flow
        that never produced one."""
        next_path = safe_next(request.session.pop(NEXT_KEY, None))  # one use
        try:
            token: Mapping[str, Any] = await self._client.authorize_access_token(request)
        except _IDP_ERRORS as exc:
            # Only the type and the OAuth error code: the message can carry text from the request.
            log.warning(
                "oidc token exchange failed", error=type(exc).__name__, code=getattr(exc, "error", None)
            )
            raise OidcFlowError("token_exchange_failed") from exc
        claims: Mapping[str, Any] | None = token.get("userinfo")  # absent when the IdP sent no id_token
        if not claims:
            raise OidcFlowError("no_id_token")

        subject = _text(claims.get("sub"))
        if subject is None or len(subject) > MAX_SUBJECT_LENGTH:
            raise OidcFlowError("invalid_subject")
        email = _email(claims)
        if email is None:
            raise OidcDeniedError("no_email", subject)

        try:
            user = await run_in_threadpool(
                self._identity.upsert_oidc_user,
                subject=subject,
                email=email,
                display_name=(_text(claims.get("name")) or email.partition("@")[0])[:MAX_NAME_LENGTH],
            )
        except UserConflictError as exc:
            raise OidcDeniedError("email_conflict", subject) from exc
        if not user.is_active:
            # Before any role change: an account an admin switched off must stay exactly as it was left.
            raise OidcDeniedError("inactive", user.id)

        roles = self._role_map.roles_for(self._groups(claims))
        await run_in_threadpool(self._identity.sync_roles, user.id, roles, "oidc")
        actor = await run_in_threadpool(self._identity.get_actor, user.id)
        if actor is None:  # deactivated between the two steps
            raise OidcDeniedError("inactive", user.id)
        return OidcSignIn(actor=actor, roles_synced=tuple(sorted(roles)), next_path=next_path)

    def _groups(self, claims: Mapping[str, Any]) -> list[str]:
        value = claims.get(self._group_claim)
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [group for group in value if isinstance(group, str)]
        # Entra ID leaves the claim out and points at the Graph API when someone is in too many groups
        # (the "overage" case); the default roles apply and an admin can see why.
        names = claims.get("_claim_names")
        log.warning(
            "the ID token has no groups: the default roles apply",
            claim=self._group_claim,
            overage=isinstance(names, dict) and self._group_claim in names,
        )
        return []


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _email(claims: Mapping[str, Any]) -> str | None:
    """The ``email`` claim, else ``preferred_username`` when it looks like an address (Entra ID often omits
    ``email`` and puts the sign-in name there). Used for contact and display only: people are identified
    by ``sub``."""
    for claim in ("email", "preferred_username"):
        value = _text(claims.get(claim))
        if value is not None and "@" in value and len(value) <= MAX_EMAIL_LENGTH:
            return value.lower()
    return None
