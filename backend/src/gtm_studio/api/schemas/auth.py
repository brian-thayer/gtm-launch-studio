"""Request and response models for ``/api/auth``."""

from typing import Literal

from pydantic import BaseModel, Field

from gtm_studio.domain.identity import Actor, Permission, RoleKind, RoleRecord, role_kind


class DevUserOption(BaseModel):
    id: str
    display_name: str
    roles: list[str]


class AuthOptions(BaseModel):
    """What the login page shows. ``dev_users`` is filled only for the dev provider."""

    provider: Literal["dev", "oidc"]
    dev_users: list[DevUserOption] = Field(default_factory=list[DevUserOption])


class DevLoginRequest(BaseModel):
    user_id: str = Field(max_length=36)  # a UUID; anything longer can't match a user


class RoleInfo(BaseModel):
    """A role the user holds, as the roles table describes it. ``kind`` tells the UI how to show it."""

    key: str
    label: str
    kind: RoleKind


class Me(BaseModel):
    id: str
    email: str
    display_name: str
    roles: list[str]
    role_info: list[RoleInfo]
    permissions: list[Permission]

    @classmethod
    def from_actor(cls, actor: Actor, role_records: list[RoleRecord]) -> "Me":
        """``role_records``: the actor's roles from the roles table (``IdentityService.describe_roles``)."""
        return cls(
            id=actor.id,
            email=actor.email,
            display_name=actor.display_name,
            roles=sorted(actor.roles),
            role_info=[
                RoleInfo(key=role.key, label=role.label, kind=role_kind(role.key)) for role in role_records
            ],
            permissions=sorted(actor.permissions),
        )
