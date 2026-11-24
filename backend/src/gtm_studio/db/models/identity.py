"""``users``, ``roles`` and ``user_roles``: who people are and what they hold (ADR-0002).

Permissions are not stored: code maps roles to permissions (``domain/identity.py``).
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from gtm_studio.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, utcnow


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    # SQLite and Postgres both let several rows have a NULL subject, so dev users don't collide.
    # Named explicitly: the naming convention would call it after its first column only.
    __table_args__ = (
        UniqueConstraint("auth_provider", "auth_subject", name="uq_users_auth_provider_subject"),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_provider: Mapped[str] = mapped_column(String(20))  # 'dev' | 'oidc'
    auth_subject: Mapped[str | None] = mapped_column(String(255), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    @validates("email")
    def _lowercase_email(self, _key: str, value: str) -> str:
        return value.strip().lower()


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20))  # 'system' | 'dev_seed' | 'catalog' | 'oidc'
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_key: Mapped[str] = mapped_column(ForeignKey("roles.key"), primary_key=True)
    granted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(20))
