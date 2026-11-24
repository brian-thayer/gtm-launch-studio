"""FastAPI application factory.

Run it with ``uvicorn gtm_studio.api.app:create_app --factory``.

Rules that keep the generated OpenAPI contract stable (see ``api/openapi.py``):
- Every router sets ``tags``. Operation IDs are ``<tag>_<function name>``.
- The set of routes and their schemas never depends on ``Settings``. Mount routes unconditionally and
  decide inside the handler (a disabled feature answers 404), so ``gtm openapi`` is the same everywhere.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from gtm_studio import __version__
from gtm_studio.api.routes import health
from gtm_studio.settings import Settings

API_PREFIX = "/api"


def _operation_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}_{route.name}"


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
    )
    app.state.settings = settings
    if settings.cors_origins:
        # Off by default: the Vite proxy makes the browser see one origin. Middleware adds no routes, so
        # this keeps the OpenAPI schema independent of settings.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,  # the session cookie (S06)
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-Requested-With"],
        )
    app.include_router(health.router, prefix=API_PREFIX)
    return app
