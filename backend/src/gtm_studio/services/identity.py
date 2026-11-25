"""Identity use cases: seeding the development users, resolving a session to an ``Actor``, and recording
logins. Services see only the ports in ``services/ports.py``."""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gtm_studio.domain.audit import AuditAction
from gtm_studio.domain.identity import Actor, AuthProviderName, UserRecord
from gtm_studio.services.ports import UnitOfWorkFactory

_ROLE_KEY = re.compile(r"[a-z][a-z0-9_]{0,49}")
USER_ENTITY = "user"  # audit_events.entity_type for a user


class DevUserSeed(BaseModel):
    """One entry of ``config/dev_users.yaml``. The ID is fixed so tests and e2e runs are stable."""

    model_config = ConfigDict(extra="forbid")

    id: str
    email: str
    display_name: str = Field(min_length=1)
    roles: list[str] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _uuid(cls, value: str) -> str:
        return str(uuid.UUID(value))  # canonical lowercase form; raises ValueError when malformed

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError("not an email address")
        return value

    @field_validator("roles")
    @classmethod
    def _role_keys(cls, value: list[str]) -> list[str]:
        for key in value:
            if not _ROLE_KEY.fullmatch(key):
                raise ValueError(f"role key {key!r} must be lowercase letters, digits and underscores")
        return list(dict.fromkeys(value))


class DevUsersFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    users: list[DevUserSeed]


@dataclass(frozen=True)
class SeedSummary:
    users_created: int
    users_updated: int
    users_unchanged: int
    roles_created: int


class SeedError(Exception):
    """The seed file can't be used (unreadable, malformed, or in conflict with an existing user). The
    message is meant for the person running ``gtm seed dev-users``."""


def load_dev_users(path: Path) -> list[DevUserSeed]:
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        return DevUsersFile.model_validate(data).users
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise SeedError(f"{path}: {exc}") from exc


def _utc_now() -> datetime:
    return datetime.now(UTC)


class IdentityService:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Callable[[], datetime] = _utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def seed_dev_users(self, path: Path) -> SeedSummary:
        """Create or update the users in ``path`` and the roles they need. Safe to run again: a second
        run with an unchanged file changes nothing. Users and roles not in the file are left alone."""
        seeds = load_dev_users(path)
        users_created = users_updated = users_unchanged = roles_created = 0
        with self._uow_factory() as uow:
            repo = uow.identity
            for seed in seeds:
                for role in seed.roles:
                    if repo.ensure_role(role, label=role, source="dev_seed"):
                        roles_created += 1
            for seed in seeds:
                existing = repo.get_user(seed.id)
                owner = repo.get_user_by_email(seed.email)
                if owner is not None and owner.id != seed.id:
                    raise SeedError(f"{path}: {seed.email} already belongs to a different user ({owner.id})")
                wanted = UserRecord(
                    id=seed.id,
                    email=seed.email,
                    display_name=seed.display_name,
                    is_active=True,
                    auth_provider="dev",
                    auth_subject=None,
                    roles=frozenset(seed.roles),
                )
                if existing is None:
                    users_created += 1
                elif _same_user(existing, wanted):
                    users_unchanged += 1
                    continue
                else:
                    users_updated += 1
                repo.upsert_user(wanted)
                repo.set_roles(seed.id, seed.roles, source="dev_seed")
        return SeedSummary(users_created, users_updated, users_unchanged, roles_created)

    def get_actor(self, user_id: str) -> Actor | None:
        """The person behind a session. None when the user doesn't exist or has been deactivated."""
        with self._uow_factory() as uow:
            user = uow.identity.get_user(user_id)
        return user.to_actor() if user is not None and user.is_active else None

    def list_active_users(self) -> list[UserRecord]:
        with self._uow_factory() as uow:
            return uow.identity.list_active_users()

    def record_login(self, actor: Actor, provider: AuthProviderName) -> None:
        """A person signed in: stamp their last login and audit it, in one transaction."""
        with self._uow_factory() as uow:
            uow.identity.set_last_login(actor.id, self._clock())
            uow.audit.record(
                actor, AuditAction.AUTH_LOGIN, USER_ENTITY, actor.id, details={"provider": provider}
            )

    def record_logout(self, actor: Actor) -> None:
        with self._uow_factory() as uow:
            uow.audit.record(actor, AuditAction.AUTH_LOGOUT, USER_ENTITY, actor.id)

    def record_login_denied(self, user_id: str, provider: AuthProviderName) -> None:
        """Someone tried to sign in as a user who doesn't exist or is inactive. There is no actor; the
        user ID they tried is the entity (the login schema caps it at 36 characters)."""
        with self._uow_factory() as uow:
            uow.audit.record(
                None, AuditAction.AUTH_LOGIN_DENIED, USER_ENTITY, user_id, details={"provider": provider}
            )


def _same_user(a: UserRecord, b: UserRecord) -> bool:
    """Whether the stored user already matches the seed (last login is not part of the seed)."""
    return (
        a.email == b.email
        and a.display_name == b.display_name
        and a.is_active == b.is_active
        and a.auth_provider == b.auth_provider
        and a.auth_subject == b.auth_subject
        and a.roles == b.roles
    )
