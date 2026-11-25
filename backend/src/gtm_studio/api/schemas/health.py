"""Response model for ``GET /api/health``."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    env: Literal["dev", "test", "production"]
    db: Literal["ok", "error"]
    catalog: Literal["ok", "missing"]
    catalog_version: str | None
