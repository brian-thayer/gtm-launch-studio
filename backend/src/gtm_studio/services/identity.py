"""Identity use cases: seeding the development users, resolving a session to an ``Actor``, and recording
logins. Services see only the ports in ``services/ports.py``."""

import uuid
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import structlog

from gtm_studio.domain.audit import AuditAction
from gtm_studio.domain.clock import utcnow
from gtm_studio.domain.errors import ConflictError
from gtm_studio.domain.identity import (
    Actor,
    AuthProviderName,
    DevUserSeed,
    RoleRecord,
    RoleSource,
    UserRecord,
    check_role_key,
)
from gtm_studio.services.ports import UnitOfWorkFactory

log = structlog.get_logger()

USER_ENTITY = "user"  # audit_events.entity_type for a user


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


class UserConflictError(ConflictError):
    """An identity provider reported an email that already belongs to a different user. People are never
    matched by email (a mutable, sometimes unverified claim): taking over an account that way is how a
    hostile IdP tenant or a renamed mailbox would get someone else's roles."""


class IdentityService:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Callable[[], datetime] = utcnow) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def seed_dev_users(self, seeds: Sequence[DevUserSeed]) -> SeedSummary:
        """Create or update these users (``auth.dev_users.load_dev_users`` reads them) and the roles they
        need, in one transaction. Safe to run again: an unchanged file changes nothing and audits nothing.
        Users and roles not in the file are left alone. Each change is audited with no actor (system):
        ``user.seeded``, ``user.updated`` and ``user.roles_set``."""
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
                    raise SeedError(f"{seed.email} already belongs to a different user ({owner.id})")
                wanted = UserRecord(
                    id=seed.id,
                    email=seed.email,
                    display_name=seed.display_name,
                    is_active=True,
                    auth_provider="dev",
                    auth_subject=None,
                    roles=frozenset(seed.roles),
                )
                if existing is not None and _same_user(existing, wanted):
                    users_unchanged += 1
                    continue
                repo.upsert_user(wanted)
                added, removed = repo.set_roles(seed.id, seed.roles, source="dev_seed")
                if existing is None:
                    users_created += 1
                    uow.audit.record(
                        None, AuditAction.USER_SEEDED, USER_ENTITY, seed.id, details={"provider": "dev"}
                    )
                else:
                    users_updated += 1
                    if fields := _changed_profile_fields(existing, wanted):
                        uow.audit.record(
                            None,
                            AuditAction.USER_UPDATED,
                            USER_ENTITY,
                            seed.id,
                            details={"provider": "dev", "fields": fields},
                            before=_profile(existing, fields),
                            after=_profile(wanted, fields),
                        )
                if added or removed:
                    uow.audit.record(
                        None,
                        AuditAction.USER_ROLES_SET,
                        USER_ENTITY,
                        seed.id,
                        details={"added": sorted(added), "removed": sorted(removed)},
                    )
        return SeedSummary(users_created, users_updated, users_unchanged, roles_created)

    def user_exists(self, user_id: str) -> bool:
        """Whether any user, active or not, has this ID. Dev login uses it to tell a sign-in that names
        nobody (logged only) from one an existing user may not make (audited)."""
        with self._uow_factory() as uow:
            return uow.identity.get_user(user_id) is not None

    def get_actor(self, user_id: str) -> Actor | None:
        """The person behind a session. None when the user doesn't exist or has been deactivated."""
        with self._uow_factory() as uow:
            user = uow.identity.get_user(user_id)
        return user.to_actor() if user is not None and user.is_active else None

    def describe_roles(self, role_keys: Collection[str]) -> list[RoleRecord]:
        """The role rows for these keys (label, source, active), by key. A key with no row is left out."""
        wanted = set(role_keys)
        with self._uow_factory() as uow:
            return [role for role in uow.identity.list_roles() if role.key in wanted]

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
                # The detail reaches a client if nothing catches it, so it names no address.
                raise UserConflictError("the email already belongs to a different user")
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
        wanted = sorted(check_role_key(key) for key in set(role_keys))
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
        """Someone tried to sign in as an existing user who may not (inactive, say), or the IdP vouched for
        someone we refuse. There is no actor; the user ID or subject tried is the entity (at most 100
        characters). ``reason`` is a short code, never free text from the request. Don't call it for an ID
        that names nobody: that is logged only (ADR-0006)."""
        details: dict[str, Any] = {"provider": provider}
        if reason is not None:
            details["reason"] = reason
        with self._uow_factory() as uow:
            uow.audit.record(None, AuditAction.AUTH_LOGIN_DENIED, USER_ENTITY, user_id, details=details)


_PROFILE_FIELDS = ("email", "display_name", "is_active", "auth_provider", "auth_subject")


def _changed_profile_fields(before: UserRecord, after: UserRecord) -> list[str]:
    """The names of the fields that differ, roles and last login aside."""
    return [name for name in _PROFILE_FIELDS if getattr(before, name) != getattr(after, name)]


def _profile(user: UserRecord, fields: list[str]) -> dict[str, Any]:
    return {name: getattr(user, name) for name in fields}


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
