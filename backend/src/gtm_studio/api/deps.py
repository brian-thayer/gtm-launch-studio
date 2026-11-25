"""Shared FastAPI dependencies. Per-request wiring only: no business rules."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from gtm_studio.auth.oidc import OidcAuthProvider
from gtm_studio.db.deps import get_session as get_session  # re-export: routers import deps from here
from gtm_studio.db.deps import get_uow_factory
from gtm_studio.services.activity import ActivityService
from gtm_studio.services.catalog import CatalogService
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import Settings


def get_settings(request: Request) -> Settings:
    """The Settings instance ``create_app`` stored on the app. Override it in tests with
    ``app.dependency_overrides``."""
    settings: Settings = request.app.state.settings
    return settings


def get_activity_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> ActivityService:
    return ActivityService(uow_factory)


ActivityServiceDep = Annotated[ActivityService, Depends(get_activity_service)]


def get_catalog_service(request: Request) -> CatalogService:
    """The one ``CatalogService`` the lifespan built. It holds the loaded catalog in memory, so unlike the
    other services it is shared, not built per request from the unit-of-work factory."""
    service: CatalogService | None = getattr(request.app.state, "catalog_service", None)
    if service is None:
        raise RuntimeError("no catalog service: the app lifespan did not run (use `with TestClient(app)`)")
    return service


CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]


def get_oidc_provider(request: Request) -> OidcAuthProvider:
    """The OIDC provider the lifespan built, or 404 when the app isn't configured for OIDC (the routes are
    mounted either way so the OpenAPI schema never changes)."""
    provider: OidcAuthProvider | None = getattr(request.app.state, "oidc_provider", None)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return provider


OidcProviderDep = Annotated[OidcAuthProvider, Depends(get_oidc_provider)]
