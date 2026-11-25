"""The catalog the running app follows: read-only for anyone with ``catalog:read``, and a reload for admins.

Routers only map: the tier x gate matrix, the role sync and the validation are ``CatalogService``'s. With no
catalog loaded every ``GET`` answers 404 ``no catalog loaded`` (a ``NotFoundError`` from the service), and a
reload still works so an admin can load one after adding the files.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response, status

from gtm_studio.api.deps import CatalogServiceDep
from gtm_studio.api.schemas.catalog import (
    AssetTypeResponse,
    CatalogResponse,
    MatrixResponse,
    ReloadResponse,
)
from gtm_studio.auth.deps import require
from gtm_studio.domain.catalog import Brand
from gtm_studio.domain.identity import Actor, Permission

router = APIRouter(prefix="/catalog", tags=["catalog"])

Reader = Annotated[Actor, Depends(require(Permission.CATALOG_READ))]
NO_CATALOG: dict[int | str, dict[str, Any]] = {
    404: {"description": "No catalog is loaded (`no catalog loaded`)."}
}


@router.get("", response_model=CatalogResponse, responses=NO_CATALOG)
def overview(_: Reader, catalog: CatalogServiceDep) -> CatalogResponse:
    """The loaded catalog: version, issues, roles, gates, tiers, triggers and a summary of each asset type."""
    return CatalogResponse.from_loaded(catalog.snapshot)


@router.get("/matrix", response_model=MatrixResponse, responses=NO_CATALOG)
def matrix(_: Reader, catalog: CatalogServiceDep) -> MatrixResponse:
    """Tiers (biggest first) by gates (in order): the core assets in each cell, plus each tier's optional
    assets and triggers. Computed by the backend; the UI only renders it."""
    return MatrixResponse.from_view(catalog.matrix_view())


@router.get(
    "/asset-types/{key}",
    response_model=AssetTypeResponse,
    responses={404: {"description": "No catalog is loaded, or it has no such asset type."}},
)
def asset_type(
    key: Annotated[str, Path(max_length=100)], _: Reader, catalog: CatalogServiceDep
) -> AssetTypeResponse:
    """One asset type: its spec, prompt, rubric, gold examples and who may approve it."""
    return AssetTypeResponse.from_view(catalog.asset_type_view(key))


@router.get("/brand", response_model=Brand, responses=NO_CATALOG)
def brand(_: Reader, catalog: CatalogServiceDep) -> Brand:
    """Voice, claims and legal guidance, terminology and the visual identity."""
    return catalog.brand_view()


@router.post(
    "/reload",
    response_model=ReloadResponse,
    responses={
        409: {"model": ReloadResponse, "description": "The files have errors: the old catalog stays."}
    },
)
def reload(
    actor: Annotated[Actor, Depends(require(Permission.CATALOG_ADMIN))],
    catalog: CatalogServiceDep,
    response: Response,
) -> ReloadResponse:
    """Read the catalog files again. Valid files replace the loaded catalog (and sync the approver roles).
    Files with errors change nothing: the response is a 409 listing every issue. Either way it is audited.
    This reloads the process that served the request only."""
    result = catalog.reload(actor)
    if not result.ok:
        response.status_code = status.HTTP_409_CONFLICT
    return ReloadResponse.model_validate(result)
