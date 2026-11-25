"""Application settings. The only place environment variables are read.

There is deliberately no module-level ``Settings()`` instance and no ``lru_cache``: ``create_app`` and
the CLI each build one and pass it down, so tests can build as many differently configured apps as
they need.
"""

import re
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/src/gtm_studio/settings.py -> parents[3] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / "backend" / ".env"

# Public on purpose: it only has to be good enough for a local run, and production refuses it.
DEV_SESSION_SECRET = "dev-only-session-secret-not-for-hosting"  # noqa: S105 (public on purpose, see above)
MIN_SESSION_SECRET_LENGTH = 32

_SQLITE_PREFIX = "sqlite:///"
# 'sqlite:///', and driver-qualified forms such as 'sqlite+pysqlite:///'.
_SQLITE_URL = re.compile(r"(?P<prefix>sqlite(?:\+\w+)?:///)(?P<target>.*)", re.DOTALL)


def _resolve_path(value: Path) -> Path:
    """Relative paths mean 'relative to the repo root', never to the process's working directory."""
    return value if value.is_absolute() else (REPO_ROOT / value).resolve()


def _http_url(value: str) -> str:
    """An http(s) URL without a trailing '/': the issuer is joined with a path and the frontend URL with
    the page to return to, so a stray slash would double up."""
    value = value.strip()
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("must be an http(s) URL")
    return value.rstrip("/")


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
    # Signs the session cookie. The default is public (it is in the repository): fine for a local run,
    # refused in production. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
    session_secret: SecretStr = SecretStr(DEV_SESSION_SECRET)
    # 'dev' lists the seeded users on the login page (no password). 'oidc' signs in through an identity
    # provider (Entra ID, Okta, ...) and needs the four oidc_* values marked (required) below.
    auth_provider: Literal["dev", "oidc"] = "dev"
    oidc_issuer: str | None = None  # (required) e.g. https://login.microsoftonline.com/<tenant>/v2.0
    oidc_client_id: str | None = None  # (required)
    oidc_client_secret: SecretStr | None = None  # (required)
    # (required) Where the IdP sends the browser back: <public origin>/api/auth/oidc/callback. It must be
    # registered at the IdP exactly as written here.
    oidc_redirect_url: str | None = None
    oidc_scopes: str = "openid email profile"
    oidc_group_claim: str = "groups"  # the ID-token claim holding the person's groups
    # Which roles each IdP group gives (see config/oidc_roles.example.yaml). Read when the API starts. Unset
    # means oidc_roles.yaml in config_dir: read it through ``oidc_role_map_file``.
    oidc_role_map_path: Path | None = None
    # Where the browser lands after signing in: the frontend's own origin (the Vite dev server locally).
    frontend_base_url: str = "http://localhost:5173"

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

    @field_validator("oidc_role_map_path")
    @classmethod
    def _absolute_role_map_path(cls, value: Path | None) -> Path | None:
        return None if value is None else _resolve_path(value)

    @property
    def oidc_role_map_file(self) -> Path:
        """The group -> role map: ``oidc_role_map_path``, else ``oidc_roles.yaml`` in ``config_dir``."""
        return self.oidc_role_map_path or self.config_dir / "oidc_roles.yaml"

    @field_validator("oidc_issuer", "oidc_redirect_url")
    @classmethod
    def _optional_url(cls, value: str | None) -> str | None:
        """Blank means unset (an empty ``GTM_OIDC_ISSUER=`` line), so the 'required for OIDC' check below
        reports it by name."""
        return None if value is None or not value.strip() else _http_url(value)

    @field_validator("frontend_base_url")
    @classmethod
    def _required_url(cls, value: str) -> str:
        return _http_url(value)

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

    @model_validator(mode="after")
    def _production_is_safe(self) -> Self:
        """Hosted use must not be able to log in without a password or sign cookies with a public key.

        ``Settings.defaults()`` builds with ``model_construct``, which skips this on purpose: it is always
        ``env='dev'``.
        """
        if self.env != "production":
            return self
        if self.auth_provider == "dev":
            raise ValueError(
                "auth_provider 'dev' (passwordless login) is not allowed when env is 'production'"
            )
        secret = self.session_secret.get_secret_value()
        if secret == DEV_SESSION_SECRET:
            raise ValueError("set session_secret (GTM_SESSION_SECRET): the built-in one is public")
        if len(secret) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(f"session_secret must be at least {MIN_SESSION_SECRET_LENGTH} characters")
        return self

    @model_validator(mode="after")
    def _oidc_is_configured(self) -> Self:
        """Signing in through an identity provider needs four values; say which ones are missing. Declared
        after the production check on purpose: a hosted deployment is told about its secret first."""
        if self.auth_provider != "oidc":
            return self
        missing = [
            f"GTM_{name.upper()}"
            for name, value in (
                ("oidc_issuer", self.oidc_issuer),
                ("oidc_client_id", (self.oidc_client_id or "").strip()),
                (
                    "oidc_client_secret",
                    self.oidc_client_secret.get_secret_value().strip() if self.oidc_client_secret else None,
                ),
                ("oidc_redirect_url", self.oidc_redirect_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"auth_provider 'oidc' also needs {', '.join(missing)}")
        if self.env == "production":
            # The client secret travels to the token endpoint and the session cookie is Secure: plain http
            # would leak the first and make the second useless.
            for name, url in (
                ("oidc_issuer", self.oidc_issuer),
                ("oidc_redirect_url", self.oidc_redirect_url),
                ("frontend_base_url", self.frontend_base_url),
            ):
                if url is None or not url.startswith("https://"):
                    raise ValueError(f"{name} must be an https URL when env is 'production'")
        return self
