"""Identity use cases: seeding the development users, resolving a session to an ``Actor``, and recording
logins. Services see only the ports in ``services/ports.py``."""

import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gtm_studio.domain.audit import AuditAction
from gtm_studio.domain.identity import ROLE_KEY, Actor, AuthProviderName, RoleSource, UserRecord
from gtm_studio.services.ports import UnitOfWorkFactory

log = structlog.get_logger()

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
            if not ROLE_KEY.fullmatch(key):
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


@dataclass(frozen=True)
class RoleSync:
    """What ``IdentityService.sync_roles`` changed."""

    added: frozenset[str]
    removed: frozenset[str]


class SeedError(Exception):
    """The seed file can't be used (unreadable, malformed, or in conflict with an existing user). The
    message is meant for the person running ``gtm seed dev-users``."""


class UserConflictError(Exception):
    """An identity provider reported an email that already belongs to a different user. People are never
    matched by email (a mutable, sometimes unverified claim): taking over an account that way is how a
    hostile IdP tenant or a renamed mailbox would get someone else's roles."""


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

    def upsert_oidc_user(self, *, subject: str, email: str, display_name: str) -> UserRecord:
        """The user an identity provider vouches for, created on the first sign-in (just-in-time) and
        kept in step with the IdP's email and name afterwards. People are found by ``(oidc, subject)``
        only. Raises ``UserConflictError`` when the email is already another user's.

        A deactivated user is returned as they are: nothing about them changes, so an account an admin
        switched off stays exactly as it was left. The caller refuses the sign-in."""
        email = email.strip().lower()
        with self._uow_factory() as uow:
            repo = uow.identity
            existing = repo.get_user_by_subject("oidc", subject)
            if existing is not None and not existing.is_active:
                return existing  # checked first: whatever else is off, the refusal is for being inactive
            owner = repo.get_user_by_email(email)
            if owner is not None and (existing is None or owner.id != existing.id):
                raise UserConflictError(f"{email} already belongs to a different user")
            if existing is None:
                created = UserRecord(
                    id=str(uuid.uuid4()),
                    email=email,
                    display_name=display_name,
                    is_active=True,
                    auth_provider="oidc",
                    auth_subject=subject,
                    roles=frozenset(),
                )
                repo.upsert_user(created)
                uow.audit.record(
                    None, AuditAction.USER_PROVISIONED, USER_ENTITY, created.id, details={"provider": "oidc"}
                )
                return created
            if (existing.email, existing.display_name) == (email, display_name):
                return existing
            updated = replace(existing, email=email, display_name=display_name)
            repo.upsert_user(updated)
            uow.audit.record(
                None,
                AuditAction.USER_UPDATED,
                USER_ENTITY,
                existing.id,
                details={"provider": "oidc", "fields": _changed_profile_fields(existing, updated)},
                before={"email": existing.email, "display_name": existing.display_name},
                after={"email": updated.email, "display_name": updated.display_name},
            )
            return updated

    def sync_roles(self, user_id: str, role_keys: Collection[str], source: RoleSource) -> RoleSync:
        """Make the user's grants from ``source`` exactly ``role_keys``. Grants from any other source are
        untouched, so a role an admin gave someone by hand outlives the IdP no longer asking for it.

        A key no role row exists for yet (for example an approver role the catalog hasn't declared) is
        created **inactive** and logged: an inactive role grants nothing, so a typo or an early mapping in
        the IdP config never hands out access by accident. Raises ``ValueError`` for a malformed key."""
        wanted = sorted(set(role_keys))
        for key in wanted:
            if not ROLE_KEY.fullmatch(key):
                raise ValueError(f"role key {key!r} must be lowercase letters, digits and underscores")
        with self._uow_factory() as uow:
            repo = uow.identity
            for key in wanted:
                if repo.ensure_role(key, label=key, source=source, active=False):
                    log.warning("created an inactive role: nothing declares it yet", role=key, source=source)
            added, removed = repo.sync_source_roles(user_id, wanted, source=source)
            if added or removed:
                uow.audit.record(
                    None,
                    AuditAction.USER_ROLES_SYNCED,
                    USER_ENTITY,
                    user_id,
                    details={"source": source, "added": sorted(added), "removed": sorted(removed)},
                )
        return RoleSync(added=added, removed=removed)

    def record_login(
        self, actor: Actor, provider: AuthProviderName, *, roles_synced: Collection[str] | None = None
    ) -> None:
        """A person signed in: stamp their last login and audit it, in one transaction. ``roles_synced``
        is what the identity provider's groups mapped to (OIDC only)."""
        details: dict[str, Any] = {"provider": provider}
        if roles_synced is not None:
            details["roles_synced"] = sorted(roles_synced)
        with self._uow_factory() as uow:
            uow.identity.set_last_login(actor.id, self._clock())
            uow.audit.record(actor, AuditAction.AUTH_LOGIN, USER_ENTITY, actor.id, details=details)

    def record_logout(self, actor: Actor) -> None:
        with self._uow_factory() as uow:
            uow.audit.record(actor, AuditAction.AUTH_LOGOUT, USER_ENTITY, actor.id)

    def record_login_denied(
        self, user_id: str, provider: AuthProviderName, reason: str | None = None
    ) -> None:
        """Someone tried to sign in as a user who doesn't exist or is inactive. There is no actor; the
        user ID they tried is the entity (at most 100 characters). ``reason`` is a short code, never free
        text from the request."""
        details: dict[str, Any] = {"provider": provider}
        if reason is not None:
            details["reason"] = reason
        with self._uow_factory() as uow:
            uow.audit.record(None, AuditAction.AUTH_LOGIN_DENIED, USER_ENTITY, user_id, details=details)


def _changed_profile_fields(before: UserRecord, after: UserRecord) -> list[str]:
    fields: list[str] = []
    if before.email != after.email:
        fields.append("email")
    if before.display_name != after.display_name:
        fields.append("display_name")
    return fields


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
