"""The one place a domain exception becomes an HTTP response (ADR-0006). Routers never catch them.

Exception handlers add nothing to the OpenAPI schema, so registering them is safe in ``create_app``. Any
other exception is left alone: it becomes the plain 500 that ``RequestContextMiddleware`` answers with,
which still carries the request ID.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from gtm_studio.domain.errors import (
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
    NotPermittedError,
)

STATUS_FOR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NotPermittedError: status.HTTP_403_FORBIDDEN,
}


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    # Starlette picks the handler by walking the exception's MRO, so a subclass (the audit cursor's
    # error, say) lands on its base class's entry here.
    assert isinstance(exc, DomainError)  # noqa: S101  (registered only for DomainError subclasses)
    code = next(code for kind, code in STATUS_FOR.items() if isinstance(exc, kind))
    return JSONResponse({"detail": exc.detail}, status_code=code)


def register_exception_handlers(app: FastAPI) -> None:
    for kind in STATUS_FOR:
        app.add_exception_handler(kind, _domain_error)
