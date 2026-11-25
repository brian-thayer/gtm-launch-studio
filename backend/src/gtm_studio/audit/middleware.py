"""Request IDs and the access log.

Pure ASGI (not ``BaseHTTPMiddleware``): it runs the app in the same task, so the context variable it sets
is the one handlers see, and it never buffers a response. Add it **last** in ``create_app`` so it is the
outermost middleware: even a CSRF rejection or a CORS preflight then carries an ``X-Request-ID`` and gets
an access line.

The access line holds the method, the path (``scope["path"]``: no query string), the status, the
duration and the actor. Request and response bodies are never read, so they can't be logged.
"""

import re
import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gtm_studio.audit.context import (
    RequestContext,
    reset_request_context,
    set_request_context,
)

REQUEST_ID_HEADER = "X-Request-ID"
# What we accept from a caller (a load balancer or the frontend may set one): short and header-safe, so
# it can't smuggle a log-injection payload. Anything else is replaced by a fresh uuid4.
_ACCEPTABLE_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
_MAX_USER_AGENT = 512  # the audit_events.user_agent column length

log = structlog.get_logger("gtm_studio.access")


def _request_id_from(headers: Headers) -> str:
    inbound = headers.get(REQUEST_ID_HEADER)
    if inbound is not None and _ACCEPTABLE_REQUEST_ID.fullmatch(inbound):
        return inbound
    return str(uuid.uuid4())


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        client = scope.get("client")
        user_agent = headers.get("user-agent")
        context = RequestContext(
            request_id=_request_id_from(headers),
            ip=client[0] if client else None,
            user_agent=user_agent[:_MAX_USER_AGENT] if user_agent else None,
        )
        token = set_request_context(context)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=context.request_id, path=scope["path"], method=scope["method"]
        )
        status_code = 500  # what the client gets if the app dies before it answers
        response_started = False
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = context.request_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                # Starlette's own 500 handler sits outside this middleware, so its response would carry no
                # request ID. Answer here (same body as Starlette's), then re-raise like it does, so the
                # server logs the traceback and tests can see the error.
                if not response_started:
                    await PlainTextResponse("Internal Server Error", status_code=500)(
                        scope, receive, send_with_request_id
                    )
                raise
        finally:
            log.info(
                "request",
                method=scope["method"],
                path=scope["path"],
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                actor_id=context.actor_id,
            )
            structlog.contextvars.clear_contextvars()
            reset_request_context(token)
