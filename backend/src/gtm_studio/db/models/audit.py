"""``audit_events``: the append-only trail of who did what (ADR-0002, invariant 3).

Rows are only ever inserted. The migration adds SQLite triggers that reject UPDATE and DELETE (Postgres
uses ``REVOKE``, see docs/hosting.md). Because rows never change, the table has ``occurred_at`` in place
of ``created_at`` and no ``updated_at``.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from gtm_studio.db.base import Base, IdMixin, UTCDateTime, utcnow


class AuditEvent(IdMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
    )

    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # NULL when no signed-in person caused it (a background job, or a failed sign-in).
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    # A copy of the actor's name at the time, so the trail still reads right after a rename.
    actor_display: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100))  # 'auth.login', see domain/audit.py AuditAction
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    before_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    after_hash: Mapped[str | None] = mapped_column(String(64), default=None)
