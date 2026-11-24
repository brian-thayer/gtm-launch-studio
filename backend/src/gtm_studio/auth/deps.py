"""FastAPI dependencies that turn a session cookie into an ``Actor`` and check permissions.

``auth`` may not import ``api`` (the layers contract), so this reads what it needs from ``app.state``
directly instead of using ``api.deps``.

Every route except health, the login options and dev login must depend on ``current_actor`` (directly or
through ``require``); ``tests/api/test_auth.py`` enumerates the routes and fails when one doesn't.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from gtm_studio.auth.session import end_session, session_user_id
from gtm_studio.domain.identity import Actor, Permission
from gtm_studio.services.identity import IdentityService
from gtm_studio.services.ports import UnitOfWorkFactory


def get_identity_service(request: Request) -> IdentityService:
    uow_factory: UnitOfWorkFactory | None = getattr(request.app.state, "uow_factory", None)
    if uow_factory is None:
        raise RuntimeError(
            "no unit of work factory: the app lifespan did not run (use `with TestClient(app)`)"
        )
    return IdentityService(uow_factory)


IdentityDep = Annotated[IdentityService, Depends(get_identity_service)]


def optional_actor(request: Request, identity: IdentityDep) -> Actor | None:
    """The signed-in actor, or None. For the few routes that behave differently when signed in; it does
    not count as protection (the route-guard test ignores it)."""
    user_id = session_user_id(request.session)
    return identity.get_actor(user_id) if user_id is not None else None


def current_actor(request: Request, identity: IdentityDep) -> Actor:
    """The signed-in actor. 401 when there is no session or the user has since been deactivated."""
    user_id = session_user_id(request.session)
    actor = identity.get_actor(user_id) if user_id is not None else None
    if actor is None:
        if user_id is not None:
            end_session(request.session)  # a stale cookie: stop sending it
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    return actor


def require(*permissions: Permission) -> Callable[..., Actor]:
    """A dependency factory: the actor must hold every permission (401 without a session, else 403).

    >>> @router.get("/x")
    ... def x(actor: Annotated[Actor, Depends(require(Permission.AUDIT_READ))]): ...
    """

    def dependency(actor: Annotated[Actor, Depends(current_actor)]) -> Actor:
        if not set(permissions) <= actor.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "missing permission")
        return actor

    return dependency
