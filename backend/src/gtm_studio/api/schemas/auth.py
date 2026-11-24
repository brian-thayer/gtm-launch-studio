"""Request and response models for ``/api/auth``."""

from typing import Literal

from pydantic import BaseModel, Field

from gtm_studio.domain.identity import Actor, Permission


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


class Me(BaseModel):
    id: str
    email: str
    display_name: str
    roles: list[str]
    permissions: list[Permission]

    @classmethod
    def from_actor(cls, actor: Actor) -> "Me":
        return cls(
            id=actor.id,
            email=actor.email,
            display_name=actor.display_name,
            roles=sorted(actor.roles),
            permissions=sorted(actor.permissions),
        )
