"""CSRF defence for a cookie-session API: state-changing requests must carry a header the browser won't
add to a cross-site form post.

The header is custom, so a page on another origin can only send it after a CORS preflight, and CORS is
off unless ``GTM_CORS_ORIGINS`` allows that origin. The frontend client always sends it
(``frontend/src/api/client.ts``). Together with ``SameSite=Lax`` on the session cookie this is the whole
defence; there are no CSRF tokens.
"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

CSRF_HEADER = b"x-requested-with"
CSRF_VALUE = b"gtm-studio"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CsrfHeaderMiddleware:
    """Pure ASGI (not ``BaseHTTPMiddleware``) so it adds no per-request overhead or buffering."""

    def __init__(self, app: ASGIApp, *, prefix: str = "/api") -> None:
        self.app = app
        self._prefix = prefix

    def _needs_header(self, scope: Scope) -> bool:
        path: str = scope["path"]
        under_prefix = path == self._prefix or path.startswith(f"{self._prefix}/")
        return under_prefix and scope["method"] in _UNSAFE_METHODS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._needs_header(scope):
            sent = dict(scope["headers"]).get(CSRF_HEADER)
            if sent != CSRF_VALUE:
                response = JSONResponse({"detail": "missing CSRF header"}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
