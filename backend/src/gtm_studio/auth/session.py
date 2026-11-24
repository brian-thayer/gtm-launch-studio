"""What the signed session cookie holds. Starlette's ``SessionMiddleware`` signs and expires the cookie
(see ``api/app.py``); this module is the only code that knows its keys."""

import time
from collections.abc import MutableMapping
from typing import Any

SESSION_COOKIE = "gtm_session"
SESSION_USER_ID = "user_id"
SESSION_ISSUED_AT = "issued_at"
SESSION_MAX_AGE = 8 * 60 * 60  # seconds


def start_session(session: MutableMapping[str, Any], user_id: str, *, now: float | None = None) -> None:
    """Sign a user in. Anything already in the session is dropped first."""
    session.clear()
    session[SESSION_USER_ID] = user_id
    session[SESSION_ISSUED_AT] = int(time.time() if now is None else now)


def end_session(session: MutableMapping[str, Any]) -> None:
    session.clear()


def session_user_id(session: MutableMapping[str, Any], *, now: float | None = None) -> str | None:
    """The signed-in user's ID, or None when nobody is signed in or the session is older than
    ``SESSION_MAX_AGE`` (the cookie's own expiry is checked as well, by the middleware)."""
    user_id = session.get(SESSION_USER_ID)
    issued_at = session.get(SESSION_ISSUED_AT)
    if not isinstance(user_id, str) or not isinstance(issued_at, int):
        return None
    if (time.time() if now is None else now) - issued_at > SESSION_MAX_AGE:
        return None
    return user_id
