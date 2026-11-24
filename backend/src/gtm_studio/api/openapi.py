"""The one place the OpenAPI document is serialized.

``gtm openapi`` writes this text to ``frontend/openapi.json``, and the contract test (S04) compares the
committed file against the same function. Sharing it means the two can never disagree on formatting.
"""

import json

from fastapi import FastAPI


def render_openapi(app: FastAPI) -> str:
    """Deterministic JSON: sorted keys, 2-space indent, ASCII only, LF line endings, trailing newline."""
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
