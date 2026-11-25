"""Ways to sign in. ``DevAuthProvider`` lists the seeded users; ``OidcAuthProvider`` (``auth/oidc.py``)
signs people in through an identity provider (ADR-0002). A provider never starts a session itself: the
route does, once a provider vouches for someone."""

from typing import Any, Protocol

from gtm_studio.domain.identity import Actor
from gtm_studio.services.identity import IdentityService


class AuthProvider(Protocol):
    name: str

    def login_options(self) -> dict[str, Any]:
        """What the login page needs to render (unauthenticated)."""
        ...


class DevAuthProvider:
    """Pick any seeded user, no password. Never usable in production (``Settings`` refuses it)."""

    name = "dev"

    def __init__(self, identity_service: IdentityService) -> None:
        self._identity = identity_service

    def login_options(self) -> dict[str, Any]:
        users = self._identity.list_active_users()
        return {
            "provider": self.name,
            "dev_users": [
                {"id": u.id, "display_name": u.display_name, "roles": sorted(u.roles)} for u in users
            ],
        }

    def authenticate(self, user_id: str) -> Actor | None:
        """The actor for a seeded user, or None when the user is unknown or inactive."""
        return self._identity.get_actor(user_id)
