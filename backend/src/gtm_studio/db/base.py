"""Declarative base, shared column mixins and the one custom column type.

Everything here is portable between SQLite and Postgres. The naming convention gives every constraint
a deterministic name, which Alembic's batch mode (SQLite's copy-and-rename ALTER) needs in order to
drop or alter a constraint later.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, DateTime, MetaData, String, event
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column
from sqlalchemy.types import TypeDecorator

from gtm_studio.domain.clock import utcnow as utcnow  # re-export: `from gtm_studio.db.base import utcnow`

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_id() -> str:
    return str(uuid.uuid4())


class UTCDateTime(TypeDecorator[datetime]):
    """``DateTime(timezone=True)`` that always hands back timezone-aware UTC.

    SQLite has no timezone-aware type: it stores the wall-clock text and returns naive datetimes, while
    Postgres returns aware ones. This makes both behave the same, and refuses naive values on the way in
    so a local time can never be stored as if it were UTC. In migrations it is plain
    ``sa.DateTime(timezone=True)`` (``migrations/env.py`` renders it that way).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: timestamps must be timezone-aware (use utcnow())")
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    """A UUID4 string primary key, assigned in Python."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class TimestampMixin:
    """``created_at`` and ``updated_at``, set in Python (never by the database) as UTC.

    An ORM insert sets both from **one** clock read (``_stamp_insert``), so a new row's ``updated_at``
    equals its ``created_at``. The column defaults only cover a Core ``insert()``, which the ORM event
    doesn't see."""

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


@event.listens_for(TimestampMixin, "before_insert", propagate=True)
def _stamp_insert(_mapper: Mapper[Any], _connection: Connection, target: TimestampMixin) -> None:
    # A value the caller set is kept; a missing updated_at follows created_at.
    target.created_at = target.created_at or utcnow()
    target.updated_at = target.updated_at or target.created_at
