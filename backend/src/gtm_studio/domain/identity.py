"""Identity, permissions and approval rights. Pure: no IO, no framework.

Code maps roles to permissions (ADR-0002). Roles themselves come from three places: the two system roles
below, the approver roles a catalog declares (S15), and the dev seed. Whatever is not a system role is an
*approver* role.

``Permission`` says what a person may do in the app. Whether they may approve one particular gate's assets
is a separate question, answered by ``can_approve`` from the gate's ``approver_roles``.
"""

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

AuthProviderName = Literal["dev", "oidc"]
RoleSource = Literal["system", "dev_seed", "catalog", "oidc"]

ADMIN_ROLE = "admin"
VIEWER_ROLE = "viewer"
SYSTEM_ROLES: frozenset[str] = frozenset({ADMIN_ROLE, VIEWER_ROLE})

ROLE_KEY = re.compile(r"[a-z][a-z0-9_]{0,49}")
"""What a role key may look like (``roles.key`` is 50 characters)."""


class Permission(StrEnum):
    SOLUTION_READ = "solution:read"
    CONTEXT_WRITE = "context:write"
    IMPORT_RUN = "import:run"
    ASSET_GENERATE = "asset:generate"
    ASSET_REVIEW = "asset:review"
    AUDIT_READ = "audit:read"
    CATALOG_READ = "catalog:read"
    CATALOG_ADMIN = "catalog:admin"
    USER_ADMIN = "user:admin"


_READ: frozenset[Permission] = frozenset({Permission.SOLUTION_READ, Permission.CATALOG_READ})
_APPROVER: frozenset[Permission] = _READ | {
    Permission.CONTEXT_WRITE,
    Permission.IMPORT_RUN,
    Permission.ASSET_GENERATE,
    Permission.ASSET_REVIEW,
}


def permissions_for(role_keys: Iterable[str]) -> frozenset[Permission]:
    """The union of what each role allows.

    ``admin`` is everything. ``viewer`` is read-only. Any other role is an approver role: read access,
    plus working on context and assets and reviewing them. No roles at all means no permissions.
    """
    granted: set[Permission] = set()
    for key in role_keys:
        if key == ADMIN_ROLE:
            return frozenset(Permission)
        granted |= _READ if key == VIEWER_ROLE else _APPROVER
    return frozenset(granted)


@dataclass(frozen=True)
class Actor:
    """The authenticated person behind a request. Every state change is attributed to one."""

    id: str
    email: str
    display_name: str
    roles: frozenset[str]

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.roles)


@dataclass(frozen=True)
class UserRecord:
    """A user as the identity repository stores it (``roles`` are the active ones they hold)."""

    id: str
    email: str
    display_name: str
    is_active: bool
    auth_provider: AuthProviderName
    auth_subject: str | None
    roles: frozenset[str]
    last_login_at: datetime | None = None

    def to_actor(self) -> Actor:
        return Actor(id=self.id, email=self.email, display_name=self.display_name, roles=self.roles)


@dataclass(frozen=True)
class OidcRoleMap:
    """Which roles an identity provider's groups give (``config/oidc_roles.yaml``).

    A group is matched exactly (case-sensitive), by whatever the IdP puts in its groups claim: a name for
    Okta, usually an object ID for Entra ID. A person in no mapped group gets ``default_roles``.
    """

    group_to_roles: Mapping[str, frozenset[str]]
    default_roles: frozenset[str]

    def roles_for(self, groups: Iterable[str]) -> frozenset[str]:
        mapped: set[str] = set()
        for group in groups:
            mapped |= self.group_to_roles.get(group, frozenset())
        return frozenset(mapped) or self.default_roles


def can_approve(actor: Actor, approver_roles: Collection[str]) -> bool:
    """True only if ``actor`` holds one of ``approver_roles`` (a gate's approvers) and may review at all.

    ``admin`` does **not** imply approval. Administering users and the catalog must not also let someone
    approve what the people accountable for a gate are meant to approve (separation of duties). An
    admin approves only when they have been given one of the gate's approver roles as well.
    """
    if Permission.ASSET_REVIEW not in actor.permissions:
        return False  # e.g. a catalog that listed "viewer" as an approver still can't make a viewer one
    return not actor.roles.isdisjoint(approver_roles)
