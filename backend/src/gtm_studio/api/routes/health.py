"""Liveness endpoint. Unauthenticated by design: load balancers and the dev proxy call it."""

from typing import Annotated

from fastapi import APIRouter, Depends

from gtm_studio import __version__
from gtm_studio.api.deps import get_settings
from gtm_studio.api.schemas.health import HealthResponse
from gtm_studio.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, env=settings.env)
