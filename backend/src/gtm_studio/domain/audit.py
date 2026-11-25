"""The audit trail's vocabulary. Pure: no IO, no framework (ADR-0002).

Every state change writes one event, in the same transaction as the change. Events are append-only: the
table rejects UPDATE and DELETE.
"""

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

SYSTEM_ACTOR_DISPLAY = "system"
"""``actor_display`` when no signed-in person caused the event: a background job, or a failed sign-in."""


class AuditAction(StrEnum):
    """What happened, as ``<area>.<verb>`` (lowercase, snake_case verb). Each step adds the actions of the
    state changes it introduces, for example ``catalog.reloaded`` or ``asset.approved``. The stored value
    is the plain string, so renaming a member's *name* is safe and changing its value is not."""

    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGIN_DENIED = "auth.login_denied"  # an unknown or inactive user tried to sign in (no actor)


def canonical_hash(obj: Any) -> str:
    """sha256 (hex) of ``obj`` as canonical JSON: sorted keys, compact separators, UTF-8.

    Equal data gives an equal hash whatever the key order. Only plain JSON values are accepted (dict,
    list, str, int, float, bool, None): anything else raises ``TypeError`` rather than being stringified,
    because a stringified set or datetime would hash differently from run to run. Convert first, for
    example ``model.model_dump(mode="json")``.
    """
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEventView:
    """A stored audit event, as the activity API shows it."""

    id: str
    occurred_at: datetime
    actor_user_id: str | None
    actor_display: str
    action: str
    entity_type: str
    entity_id: str
    request_id: str | None
    ip: str | None
    user_agent: str | None
    details: dict[str, Any]
    before_hash: str | None
    after_hash: str | None


@dataclass(frozen=True)
class AuditFilters:
    """Narrow an audit query. Every field that is set must match; ``action_prefix`` matches the start of
    the action (``asset.`` finds every asset action)."""

    actor_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    action_prefix: str | None = None


class InvalidCursorError(ValueError):
    """The cursor is not one this API issued."""


def encode_cursor(occurred_at: datetime, event_id: str) -> str:
    """The opaque position after an event: URL-safe base64 of ``<occurred_at ISO>|<id>``."""
    raw = f"{occurred_at.isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Inverse of ``encode_cursor``. Raises ``InvalidCursorError`` for anything else, including a naive
    timestamp (stored times are always timezone-aware)."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        stamp, separator, event_id = raw.partition("|")
        if not separator or not event_id:
            raise ValueError("no separator")
        occurred_at = datetime.fromisoformat(stamp)
    except (ValueError, binascii.Error) as exc:  # UnicodeError is a ValueError
        raise InvalidCursorError("invalid cursor") from exc
    if occurred_at.tzinfo is None:
        raise InvalidCursorError("invalid cursor")
    return occurred_at, event_id
