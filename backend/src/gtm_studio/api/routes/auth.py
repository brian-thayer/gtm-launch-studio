"""Sign in, sign out and "who am I". The routes are mounted whatever ``GTM_AUTH_PROVIDER`` is, so the
OpenAPI schema never changes: dev login simply answers 404 when the provider isn't ``dev``."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from gtm_studio.api.deps import get_settings
from gtm_studio.api.schemas.auth import AuthOptions, DevLoginRequest, Me
from gtm_studio.audit.context import bind_actor
from gtm_studio.auth.deps import IdentityDep, current_actor
from gtm_studio.auth.providers import DevAuthProvider
from gtm_studio.auth.session import end_session, start_session
from gtm_studio.domain.identity import Actor
from gtm_studio.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


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
