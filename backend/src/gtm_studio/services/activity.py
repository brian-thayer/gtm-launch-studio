"""Reading the audit trail. Who may read it is the route's permission check (``audit:read``); the one rule
that lives here is that "my activity" can never show anyone else's events."""

from dataclasses import replace

from gtm_studio.domain.audit import AuditEventView, AuditFilters
from gtm_studio.domain.identity import Actor
from gtm_studio.domain.pagination import Page
from gtm_studio.services.ports import UnitOfWorkFactory

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class ActivityService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def list_events(
        self, filters: AuditFilters, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
    ) -> Page[AuditEventView]:
        """Every event that matches, newest first. Raises ``InvalidCursorError`` for a bad cursor."""
        with self._uow_factory() as uow:
            return uow.audit.query(filters, cursor, _clamp(limit))

    def list_own_events(
        self, actor: Actor, filters: AuditFilters, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
    ) -> Page[AuditEventView]:
        """Only ``actor``'s own events. Whatever ``filters.actor_id`` says is overridden."""
        return self.list_events(replace(filters, actor_id=actor.id), cursor, limit)


def _clamp(limit: int) -> int:
    return max(1, min(limit, MAX_PAGE_SIZE))
