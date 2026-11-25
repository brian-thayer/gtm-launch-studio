"""The SQLAlchemy implementation of the ``AuditLog`` port (``services/ports.py``)."""

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from gtm_studio.audit.context import get_request_context
from gtm_studio.db.base import utcnow
from gtm_studio.db.models.audit import AuditEvent
from gtm_studio.domain.audit import (
    SYSTEM_ACTOR_DISPLAY,
    AuditEventView,
    AuditFilters,
    canonical_hash,
    decode_cursor,
    encode_cursor,
)
from gtm_studio.domain.identity import Actor
from gtm_studio.domain.pagination import Page


class _StrictlyIncreasingClock:
    """Timestamps for new events: each one later than the last this process handed out.

    On Windows the system clock ticks about every 15.6 ms, so events written back to back (typically in
    one transaction: ``asset.approved`` then its follow-up) would share a timestamp and then sort by their
    random IDs, which is not the order they happened in. Bumping a tie by a microsecond keeps "newest
    first" truthful. (Two processes can still tie; their relative order is not meaningful anyway.)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = datetime.min.replace(tzinfo=UTC)

    def now(self) -> datetime:
        with self._lock:
            stamp = max(utcnow(), self._last + timedelta(microseconds=1))
            self._last = stamp
            return stamp


_clock = _StrictlyIncreasingClock()


class SqlAuditLog:
    """Adds events to the ``Session`` it is given and **never commits**: the unit of work that owns the
    session commits the event together with the change, or rolls both back. The request fields (ID,
    address, user agent) come from the current request context (the middleware has already bounded their
    length), and are empty outside a request."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        actor: Actor | None,
        action: str,
        entity_type: str,
        entity_id: str,
        *,
        details: dict[str, Any] | None = None,
        before: Any = None,
        after: Any = None,
    ) -> None:
        context = get_request_context()
        self._session.add(
            AuditEvent(
                occurred_at=_clock.now(),
                actor_user_id=actor.id if actor is not None else None,
                actor_display=actor.display_name if actor is not None else SYSTEM_ACTOR_DISPLAY,
                action=str(action),  # a StrEnum member becomes its plain value
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=context.request_id if context is not None else None,
                ip=context.ip if context is not None else None,
                user_agent=context.user_agent if context is not None else None,
                details=dict(details) if details else {},
                before_hash=canonical_hash(before) if before is not None else None,
                after_hash=canonical_hash(after) if after is not None else None,
            )
        )
        # Flush (not commit) so a bad row, such as an actor that doesn't exist, fails here, in the caller's
        # code, and the unit of work rolls the whole change back.
        self._session.flush()

    def query(self, filters: AuditFilters, cursor: str | None, limit: int) -> Page[AuditEventView]:
        statement = select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        if filters.actor_id is not None:
            statement = statement.where(AuditEvent.actor_user_id == filters.actor_id)
        if filters.entity_type is not None:
            statement = statement.where(AuditEvent.entity_type == filters.entity_type)
        if filters.entity_id is not None:
            statement = statement.where(AuditEvent.entity_id == filters.entity_id)
        if filters.action_prefix:
            statement = statement.where(AuditEvent.action.startswith(filters.action_prefix, autoescape=True))
        if cursor is not None:
            # Keyset pagination: everything strictly after the last event of the previous page. Events
            # that share a timestamp are ordered by ID, so none is skipped or repeated.
            after_time, after_id = decode_cursor(cursor)
            statement = statement.where(
                or_(
                    AuditEvent.occurred_at < after_time,
                    and_(AuditEvent.occurred_at == after_time, AuditEvent.id < after_id),
                )
            )
        rows = list(self._session.scalars(statement.limit(limit + 1)))  # one extra: is there a next page?
        page, has_more = rows[:limit], len(rows) > limit
        next_cursor = encode_cursor(page[-1].occurred_at, page[-1].id) if has_more else None
        return Page(items=[_view(row) for row in page], next_cursor=next_cursor)


def _view(row: AuditEvent) -> AuditEventView:
    return AuditEventView(
        id=row.id,
        occurred_at=row.occurred_at,
        actor_user_id=row.actor_user_id,
        actor_display=row.actor_display,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        request_id=row.request_id,
        ip=row.ip,
        user_agent=row.user_agent,
        details=row.details,
        before_hash=row.before_hash,
        after_hash=row.after_hash,
    )
