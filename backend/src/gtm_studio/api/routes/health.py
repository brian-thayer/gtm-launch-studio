"""Health endpoint. Unauthenticated by design: load balancers and the dev proxy call it.

``status`` says the process is up. ``db`` says whether the database answered, and is reported rather
than turned into an error status so the page can show what is wrong. ``catalog`` is ``missing`` when the
app started without a catalog (a state, not a failure), and ``catalog_version`` is its version hash.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from gtm_studio import __version__
from gtm_studio.api.deps import CatalogServiceDep, get_session, get_settings
from gtm_studio.api.schemas.health import HealthResponse
from gtm_studio.db.engine import database_is_up
from gtm_studio.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    catalog: CatalogServiceDep,
) -> HealthResponse:
    version_hash = catalog.version_hash
    return HealthResponse(
        status="ok",
        version=__version__,
        env=settings.env,
        db="ok" if database_is_up(session) else "error",
        catalog="missing" if version_hash is None else "ok",
        catalog_version=version_hash,
    )
