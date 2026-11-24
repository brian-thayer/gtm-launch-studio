"""Enumerate an app's endpoints as clients see them.

FastAPI 0.165 keeps routers added with ``include_router`` as lazy wrappers: ``app.routes`` holds no
``APIRoute`` for them, and a route's own ``path`` lacks the include prefix. ``iter_route_contexts`` is
the supported way to get the effective path and the real route. This module is the only place that
touches it, so a FastAPI upgrade means one fix. Used by tests that audit every route (the S06 auth
guard) and, later, by anything that needs to list endpoints.
"""

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts


@dataclass(frozen=True)
class RouteInfo:
    path: str  # full path, including the /api prefix
    methods: frozenset[str]
    route: APIRoute | None  # None for plain Starlette routes such as the interactive docs


def list_routes(app: FastAPI) -> list[RouteInfo]:
    found: list[RouteInfo] = []
    for context in iter_route_contexts(app.routes):
        original = context.original_route
        found.append(
            RouteInfo(
                path=context.path or "",
                methods=frozenset(context.methods or ()),
                route=original if isinstance(original, APIRoute) else None,
            )
        )
    return found
