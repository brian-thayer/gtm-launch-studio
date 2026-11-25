"""Shared FastAPI dependencies. Per-request wiring only: no business rules."""

from typing import Annotated

from fastapi import Depends, Request

from gtm_studio.db.deps import get_session as get_session  # re-export: routers import deps from here
from gtm_studio.services.activity import ActivityService
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import Settings


def get_settings(request: Request) -> Settings:
    """The Settings instance ``create_app`` stored on the app. Override it in tests with
    ``app.dependency_overrides``."""
    settings: Settings = request.app.state.settings
    return settings


def get_activity_service(request: Request) -> ActivityService:
    uow_factory: UnitOfWorkFactory | None = getattr(request.app.state, "uow_factory", None)
    if uow_factory is None:
        raise RuntimeError(
            "no unit of work factory: the app lifespan did not run (use `with TestClient(app)`)"
        )
    return ActivityService(uow_factory)


ActivityServiceDep = Annotated[ActivityService, Depends(get_activity_service)]
