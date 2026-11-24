"""The committed ``frontend/openapi.json`` must match what the backend generates.

The frontend's ``src/api/schema.d.ts`` is generated from that file, so drift here means the TypeScript
client no longer describes the API. This is the contract-first loop from ``frontend/CLAUDE.md``.
"""

from gtm_studio.api.app import create_app
from gtm_studio.api.openapi import render_openapi
from gtm_studio.settings import REPO_ROOT, Settings

COMMITTED_SCHEMA = REPO_ROOT / "frontend" / "openapi.json"

DRIFT_MESSAGE = (
    "frontend/openapi.json is out of date with the backend routes or schemas. "
    "Run `uv run gtm openapi > ../frontend/openapi.json` (from backend/) then `npm run gen:api` "
    "(from frontend/), and commit both files plus src/api/schema.d.ts."
)


def test_committed_openapi_matches_the_backend() -> None:
    assert COMMITTED_SCHEMA.is_file(), f"{COMMITTED_SCHEMA} is missing. {DRIFT_MESSAGE}"
    # read_text() normalizes CRLF, which matters if git's autocrlf rewrote the file on checkout.
    committed = COMMITTED_SCHEMA.read_text(encoding="utf-8")
    generated = render_openapi(create_app(Settings.defaults()))
    assert committed == generated, DRIFT_MESSAGE
