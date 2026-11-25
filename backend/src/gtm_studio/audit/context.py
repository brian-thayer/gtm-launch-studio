"""Who is asking, for the audit trail and the logs: the request ID, the caller's address and user agent,
and (once known) the signed-in user.

The context is held in a ``ContextVar`` that ``RequestContextMiddleware`` sets for each request. It is a
**mutable** dataclass on purpose: FastAPI runs sync dependencies and handlers in a thread pool, each with
a *copy* of the context. A copy still points at the same object, so ``bind_actor`` called from a
dependency is visible to the middleware's access log, whereas ``ContextVar.set`` would not be.
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class RequestContext:
    request_id: str
    ip: str | None = None
    user_agent: str | None = None
    actor_id: str | None = None


_current: ContextVar[RequestContext | None] = ContextVar("gtm_request_context", default=None)


def get_request_context() -> RequestContext | None:
    """The current request's context. None outside a request (CLI, worker, most tests)."""
    return _current.get()


def set_request_context(context: RequestContext) -> Token[RequestContext | None]:
    return _current.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _current.reset(token)


def bind_actor(actor_id: str) -> None:
    """Record who is signed in on this request, so the access log and later audit events can say so.
    A no-op outside a request."""
    context = _current.get()
    if context is not None:
        context.actor_id = actor_id
