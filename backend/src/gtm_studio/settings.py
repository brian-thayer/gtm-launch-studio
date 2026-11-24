"""Application settings. The only place environment variables are read.

There is deliberately no module-level ``Settings()`` instance and no ``lru_cache``: ``create_app`` and
the CLI each build one and pass it down, so tests can build as many differently configured apps as
they need.
"""

import re
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/src/gtm_studio/settings.py -> parents[3] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / "backend" / ".env"

_SQLITE_PREFIX = "sqlite:///"
# 'sqlite:///', and driver-qualified forms such as 'sqlite+pysqlite:///'.
_SQLITE_URL = re.compile(r"(?P<prefix>sqlite(?:\+\w+)?:///)(?P<target>.*)", re.DOTALL)


def _resolve_path(value: Path) -> Path:
    """Relative paths mean 'relative to the repo root', never to the process's working directory."""
    return value if value.is_absolute() else (REPO_ROOT / value).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GTM_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "test", "production"] = "dev"
    db_url: str = f"{_SQLITE_PREFIX}{(REPO_ROOT / 'storage' / 'gtm_studio.db').as_posix()}"
    storage_dir: Path = REPO_ROOT / "storage"
    catalog_dir: Path = REPO_ROOT / "gtm_catalog"
    config_dir: Path = REPO_ROOT / "config"
    llm_provider: Literal["mock", "bedrock"] = "mock"
    allow_bedrock: bool = False
    aws_region: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Browser origins allowed to call the API cross-origin. Empty (the default) adds no CORS middleware:
    # the Vite dev proxy and a same-origin deployment don't need it. Set as a comma-separated list.
    # NoDecode: pydantic-settings would otherwise insist on a JSON array for a list field.
    cors_origins: Annotated[list[str], NoDecode] = []

    @classmethod
    def defaults(cls) -> Self:
        """Field defaults only: no environment variables, no .env file, no validation errors possible.

        For code whose output must not depend on where it runs, such as the OpenAPI export. Everything
        else should build ``Settings()`` so misconfiguration fails loudly at startup.
        """
        return cls.model_construct()

    @field_validator("storage_dir", "catalog_dir", "config_dir")
    @classmethod
    def _absolute_dirs(cls, value: Path) -> Path:
        return _resolve_path(value)

    @field_validator("db_url")
    @classmethod
    def _absolute_sqlite_path(cls, value: str) -> str:
        """Resolve a relative SQLite file path against the repo root. Other URLs pass through."""
        match = _SQLITE_URL.fullmatch(value)
        if match is None:
            return value
        target = match["target"]
        # '' and ':memory:' are in-memory databases and 'file:' is SQLite's URI form. A leading '/' is
        # an absolute POSIX path ('sqlite:////abs/path'), which Path.is_absolute() calls relative on Windows.
        if not target or target.startswith((":", "/", "file:")) or Path(target).is_absolute():
            return value
        return f"{match['prefix']}{_resolve_path(Path(target)).as_posix()}"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept 'https://a.example, https://b.example' (and a list). Blank entries are dropped."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, value: list[str]) -> list[str]:
        """The session cookie is sent cross-origin, so a wildcard origin would let any site use it."""
        if "*" in value:
            raise ValueError("cors_origins must list explicit origins, not '*'")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
