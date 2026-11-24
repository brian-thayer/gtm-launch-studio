"""Application settings. The only place environment variables are read.

There is deliberately no module-level ``Settings()`` instance and no ``lru_cache``: ``create_app`` and
the CLI each build one and pass it down, so tests can build as many differently configured apps as
they need.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/gtm_studio/settings.py -> parents[3] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / "backend" / ".env"

_SQLITE_PREFIX = "sqlite:///"


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
        if not value.startswith(_SQLITE_PREFIX):
            return value
        target = value.removeprefix(_SQLITE_PREFIX)
        # '' and ':memory:' are in-memory databases. A leading '/' is an absolute POSIX path
        # ('sqlite:////abs/path'), which Path.is_absolute() would call relative on Windows.
        if not target or target.startswith((":", "/")) or Path(target).is_absolute():
            return value
        return f"{_SQLITE_PREFIX}{_resolve_path(Path(target)).as_posix()}"

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
