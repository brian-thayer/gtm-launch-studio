"""Ports: the interfaces services depend on. ``db`` and ``adapters`` implement them.

Services never import ``gtm_studio.db`` (the layers contract forbids an upward import), so nothing in
this file may mention SQLAlchemy. Repository ports return domain values, never ORM objects.
"""

from collections.abc import Callable, Collection
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from gtm_studio.domain.identity import RoleSource, UserRecord


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


class UnitOfWork(Protocol):
    """One transaction. Entering it opens the work, leaving it cleanly commits, and leaving it with an
    exception rolls back. Repository ports are attached to it as attributes."""

    @property
    def identity(self) -> IdentityRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
        /,
    ) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
