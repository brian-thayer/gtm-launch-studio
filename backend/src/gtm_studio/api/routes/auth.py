"""Sign in, sign out and "who am I". The routes are mounted whatever ``GTM_AUTH_PROVIDER`` is, so the
OpenAPI schema never changes: dev login simply answers 404 when the provider isn't ``dev``, and the OIDC
routes when it isn't ``oidc``."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from gtm_studio.api.deps import OidcProviderDep, get_settings
from gtm_studio.api.schemas.auth import AuthOptions, DevLoginRequest, Me
from gtm_studio.audit.context import bind_actor
from gtm_studio.auth.deps import IdentityDep, current_actor
from gtm_studio.auth.oidc import OidcDeniedError, OidcFlowError, OidcUnavailableError
from gtm_studio.auth.providers import DevAuthProvider
from gtm_studio.auth.session import end_session, start_session
from gtm_studio.domain.identity import Actor
from gtm_studio.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "not found")


@router.get("/options", response_model=AuthOptions)
def options(settings: Annotated[Settings, Depends(get_settings)], identity: IdentityDep) -> AuthOptions:
    """Unauthenticated: what the login page needs."""
    if settings.auth_provider != "dev":
        return AuthOptions(provider=settings.auth_provider)
    return AuthOptions.model_validate(DevAuthProvider(identity).login_options())


@router.post("/dev/login", response_model=Me)
def dev_login(
    body: DevLoginRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    identity: IdentityDep,
) -> Me:
    """Sign in as a seeded user. 404 for an unknown or inactive user, and whenever the provider isn't dev.
    Both outcomes are audited (`auth.login`, `auth.login_denied`)."""
    if settings.auth_provider != "dev":
        raise _not_found()
    actor = DevAuthProvider(identity).authenticate(body.user_id)
    if actor is None:
        identity.record_login_denied(body.user_id, "dev")
        raise _not_found()
    identity.record_login(actor, "dev")
    bind_actor(actor.id)  # this request is now the actor's, for the access log
    start_session(request.session, actor.id)
    return Me.from_actor(actor)


@router.get(
    "/oidc/login",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={
        404: {"description": "OIDC is not the configured provider"},
        502: {"description": "IdP unreachable"},
    },
)
async def oidc_login(
    request: Request,
    provider: OidcProviderDep,
    next_path: Annotated[str, Query(alias="next", description="Same-site path to return to; else `/`")] = "/",
) -> RedirectResponse:
    """Start the OIDC sign-in: redirect the browser to the identity provider. Open by nature (it is how
    a session starts), but it changes nothing: ``state`` and the PKCE verifier go in the caller's own
    cookie. ``next`` is checked now and again at the callback."""
    try:
        return await provider.login_redirect(request, next_path)
    except OidcUnavailableError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "identity provider unavailable") from exc


@router.get(
    "/oidc/callback",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={404: {"description": "OIDC is not the configured provider"}},
)
async def oidc_callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    identity: IdentityDep,
    provider: OidcProviderDep,
) -> RedirectResponse:
    """Where the identity provider sends the browser back. On success: start the session, audit
    `auth.login` (with the roles the groups mapped to) and redirect to the frontend page asked for. A
    refused person is audited (`auth.login_denied`, with a reason); any failure redirects to
    `/login?error=denied|failed` and signs nobody in."""
    login_url = f"{settings.frontend_base_url}/login"
    try:
        sign_in = await provider.handle_callback(request)
    except OidcDeniedError as exc:
        await run_in_threadpool(identity.record_login_denied, exc.entity_id, "oidc", exc.reason)
        log.warning("oidc sign-in denied", reason=exc.reason)
        return RedirectResponse(f"{login_url}?error=denied", status_code=status.HTTP_302_FOUND)
    except OidcFlowError as exc:
        # Not audited: nobody is identified, the endpoint is open, and audit rows can't be deleted.
        log.warning("oidc sign-in failed", reason=exc.reason)
        return RedirectResponse(f"{login_url}?error=failed", status_code=status.HTTP_302_FOUND)
    await run_in_threadpool(identity.record_login, sign_in.actor, "oidc", roles_synced=sign_in.roles_synced)
    bind_actor(sign_in.actor.id)  # this request is now the actor's, for the access log
    start_session(request.session, sign_in.actor.id)
    return RedirectResponse(
        f"{settings.frontend_base_url}{sign_in.next_path}", status_code=status.HTTP_302_FOUND
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, actor: Annotated[Actor, Depends(current_actor)], identity: IdentityDep
) -> Response:
    identity.record_logout(actor)
    end_session(request.session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=Me)
def me(actor: Annotated[Actor, Depends(current_actor)]) -> Me:
    return Me.from_actor(actor)
