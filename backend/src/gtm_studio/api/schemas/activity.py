"""Response models for ``/api/activity``."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from gtm_studio.domain.audit import AuditEventView
from gtm_studio.domain.pagination import Page


class ActivityEvent(BaseModel):
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

    @classmethod
    def from_view(cls, view: AuditEventView) -> "ActivityEvent":
        return cls(
            id=view.id,
            occurred_at=view.occurred_at,
            actor_user_id=view.actor_user_id,
            actor_display=view.actor_display,
            action=view.action,
            entity_type=view.entity_type,
            entity_id=view.entity_id,
            request_id=view.request_id,
            ip=view.ip,
            user_agent=view.user_agent,
            details=view.details,
            before_hash=view.before_hash,
            after_hash=view.after_hash,
        )


class ActivityPage(BaseModel):
    """Newest first. Pass ``next_cursor`` back as ``cursor`` for the following page; None means the end."""

    items: list[ActivityEvent]
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: Page[AuditEventView]) -> "ActivityPage":
        return cls(items=[ActivityEvent.from_view(v) for v in page.items], next_cursor=page.next_cursor)
