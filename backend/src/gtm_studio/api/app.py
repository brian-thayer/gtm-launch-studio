"""FastAPI application factory.

Run it with ``uvicorn gtm_studio.api.app:create_app --factory``.

Rules that keep the generated OpenAPI contract stable (see ``api/openapi.py``):
- Every router sets ``tags``. Operation IDs are ``<tag>_<function name>``.
- The set of routes and their schemas never depends on ``Settings``. Mount routes unconditionally and
  decide inside the handler (a disabled feature answers 404), so ``gtm openapi`` is the same everywhere.
- ``create_app`` does no IO. The database engine is built in the lifespan, so ``gtm openapi`` and
  ``app.openapi()`` never touch it.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from starlette.middleware.sessions import SessionMiddleware

from gtm_studio import __version__
from gtm_studio.api.routes import auth, health
from gtm_studio.auth.csrf import CsrfHeaderMiddleware
from gtm_studio.auth.session import SESSION_COOKIE, SESSION_MAX_AGE
from gtm_studio.db.engine import make_engine, make_session_factory
from gtm_studio.db.uow import SqlUnitOfWork
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import DEV_SESSION_SECRET, Settings

API_PREFIX = "/api"

log = structlog.get_logger()


def _operation_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}_{route.name}"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the database for the life of the process. It does not migrate: run ``gtm db upgrade``."""
    settings: Settings = app.state.settings
    if settings.env == "dev" and settings.session_secret.get_secret_value() == DEV_SESSION_SECRET:
        # Here and not in create_app: building the app must stay silent (`gtm openapi` prints to stdout).
        log.warning("using the built-in session secret: set GTM_SESSION_SECRET before sharing this instance")
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    uow_factory: UnitOfWorkFactory = partial(SqlUnitOfWork, session_factory)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.uow_factory = uow_factory
    try:
        yield
    finally:
        engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    # Interactive docs live under /api so the dev proxy reaches them, and are off when hosted.
    expose_docs = settings.env != "production"
    app = FastAPI(
        title="GTM Launch Studio",
        version=__version__,
        docs_url=f"{API_PREFIX}/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if expose_docs else None,
        swagger_ui_oauth2_redirect_url=None,  # we don't authorize through Swagger UI
        generate_unique_id_function=_operation_id,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    # Middleware runs in reverse order of adding: CORS first (so even a CSRF 403 carries CORS headers),
    # then the CSRF header check, then the session. Middleware adds no routes, so none of this changes
    # the OpenAPI schema.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE,
        same_site="lax",
        https_only=settings.env == "production",
    )
    app.add_middleware(CsrfHeaderMiddleware, prefix=API_PREFIX)
    if settings.cors_origins:
        # Off by default: the Vite proxy makes the browser see one origin.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,  # the session cookie
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-Requested-With"],
        )
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    return app
