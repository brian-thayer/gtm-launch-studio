"""SQLAlchemy implementation of the ``IdentityRepository`` port (``services/ports.py``)."""

from collections import defaultdict
from collections.abc import Collection, Iterable
from datetime import datetime
from typing import cast

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from gtm_studio.db.models.identity import Role, User, UserRole
from gtm_studio.domain.identity import AuthProviderName, RoleSource, UserRecord


class SqlIdentityRepository:
    """Reads and writes through the ``Session`` it is given. It flushes but never commits: the unit of
    work (or, for reads, the request's session) owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- reads
    def get_user(self, user_id: str) -> UserRecord | None:
        return self._one(select(User).where(User.id == user_id))

    def get_user_by_email(self, email: str) -> UserRecord | None:
        return self._one(select(User).where(User.email == email.strip().lower()))

    def get_user_by_subject(self, provider: str, subject: str) -> UserRecord | None:
        return self._one(select(User).where(User.auth_provider == provider, User.auth_subject == subject))

    def list_active_users(self) -> list[UserRecord]:
        return self._records(select(User).where(User.is_active).order_by(User.email))

    # ---- writes
    def upsert_user(self, user: UserRecord) -> None:
        row = self._session.get(User, user.id)
        if row is None:
            row = User(id=user.id)
            self._session.add(row)
        row.email = user.email
        row.display_name = user.display_name
        row.is_active = user.is_active
        row.auth_provider = user.auth_provider
        row.auth_subject = user.auth_subject
        self._session.flush()

    def ensure_role(self, key: str, label: str, source: RoleSource, *, active: bool = True) -> bool:
        if self._session.get(Role, key) is not None:
            return False
        self._session.add(Role(key=key, label=label, source=source, active=active))
        self._session.flush()
        return True

    def set_roles(
        self, user_id: str, role_keys: Collection[str], *, source: RoleSource, granted_by: str | None = None
    ) -> None:
        wanted = set(role_keys)
        held = set(self._session.scalars(select(UserRole.role_key).where(UserRole.user_id == user_id)))
        if held - wanted:
            self._session.execute(
                delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_key.in_(held - wanted))
            )
        for key in sorted(wanted - held):
            self._session.add(
                UserRole(user_id=user_id, role_key=key, granted_by_user_id=granted_by, source=source)
            )
        self._session.flush()

    def sync_source_roles(
        self, user_id: str, role_keys: Collection[str], *, source: RoleSource
    ) -> tuple[frozenset[str], frozenset[str]]:
        wanted = set(role_keys)
        rows = self._session.execute(
            select(UserRole.role_key, UserRole.source).where(UserRole.user_id == user_id)
        )
        grants = {role_key: granted_from for role_key, granted_from in rows}  # role -> where it came from
        removed = {
            key for key, granted_from in grants.items() if granted_from == source and key not in wanted
        }
        added = wanted - grants.keys()
        if removed:
            self._session.execute(
                delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_key.in_(removed))
            )
        for key in sorted(added):
            self._session.add(UserRole(user_id=user_id, role_key=key, granted_by_user_id=None, source=source))
        self._session.flush()
        return frozenset(added), frozenset(removed)

    def set_last_login(self, user_id: str, at: datetime) -> None:
        row = self._session.get_one(User, user_id)
        row.last_login_at = at
        self._session.flush()

    # ---- helpers
    def _one(self, query: Select[User]) -> UserRecord | None:
        records = self._records(query)
        return records[0] if records else None

    def _records(self, query: Select[User]) -> list[UserRecord]:
        users = list(self._session.scalars(query))
        roles = self._active_roles([user.id for user in users])
        return [
            UserRecord(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                is_active=user.is_active,
                auth_provider=cast(AuthProviderName, user.auth_provider),
                auth_subject=user.auth_subject,
                roles=frozenset(roles[user.id]),
                last_login_at=user.last_login_at,
            )
            for user in users
        ]

    def _active_roles(self, user_ids: Iterable[str]) -> dict[str, set[str]]:
        """Role keys per user, leaving out roles that have been switched off."""
        by_user: dict[str, set[str]] = defaultdict(set)
        rows = self._session.execute(
            select(UserRole.user_id, UserRole.role_key)
            .join(Role, Role.key == UserRole.role_key)
            .where(UserRole.user_id.in_(list(user_ids)), Role.active)
        )
        for user_id, role_key in rows:
            by_user[user_id].add(role_key)
        return by_user
