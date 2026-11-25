"""Ports: the interfaces services depend on. ``db`` and ``adapters`` implement them.

Services never import ``gtm_studio.db`` (the layers contract forbids an upward import), so nothing in
this file may mention SQLAlchemy. Repository ports return domain values, never ORM objects.
"""

from collections.abc import Callable, Collection
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol, Self

from gtm_studio.domain.audit import AuditEventView, AuditFilters
from gtm_studio.domain.identity import Actor, RoleSource, UserRecord
from gtm_studio.domain.pagination import Page


class IdentityRepository(Protocol):
    """Users, roles and role grants. A user's ``roles`` are only the roles that are still active."""

    def get_user(self, user_id: str) -> UserRecord | None: ...

    def get_user_by_email(self, email: str) -> UserRecord | None: ...

    def get_user_by_subject(self, provider: str, subject: str) -> UserRecord | None: ...

    def list_active_users(self) -> list[UserRecord]:
        """Active users, ordered by email."""
        ...

    def upsert_user(self, user: UserRecord) -> None:
        """Create the user, or overwrite the one with the same ID. Does not touch roles or last login."""
        ...

    def ensure_role(self, key: str, label: str, source: RoleSource) -> bool:
        """Create the role if it doesn't exist. True when it was created."""
        ...

    def set_roles(
        self, user_id: str, role_keys: Collection[str], *, source: RoleSource, granted_by: str | None = None
    ) -> None:
        """Make the user hold exactly these roles. Every role must exist. Grants that stay keep their
        original ``granted_at``."""
        ...

    def set_last_login(self, user_id: str, at: datetime) -> None: ...


class AuditLog(Protocol):
    """The append-only trail of who did what (invariant 3)."""

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
        """Add an event to the **caller's transaction**: it commits or rolls back together with the change
        it describes, and is never committed on its own. ``actor`` is None when no signed-in person caused
        it. ``before`` and ``after`` are the entity's state, stored only as hashes (``canonical_hash``), so
        pass plain JSON values. ``details`` is stored as is: never put document text, prompts or secrets
        in it.
        """
        ...

    def query(self, filters: AuditFilters, cursor: str | None, limit: int) -> Page[AuditEventView]:
        """Events newest first. ``cursor`` is a ``next_cursor`` from the previous page (None for the first);
        a cursor that isn't one raises ``InvalidCursorError``."""
        ...


class UnitOfWork(Protocol):
    """One transaction. Entering it opens the work, leaving it cleanly commits, and leaving it with an
    exception rolls back. Repository ports are attached to it as attributes."""

    @property
    def identity(self) -> IdentityRepository: ...

    @property
    def audit(self) -> AuditLog: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
        /,
    ) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
