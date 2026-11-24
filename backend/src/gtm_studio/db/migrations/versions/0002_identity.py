"""Identity: users, roles, user_roles, and the two system roles.

Revision ID: 0002_identity
Revises: 0001_baseline
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0002_identity"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_roles")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("auth_provider", sa.String(length=20), nullable=False),
        sa.Column("auth_subject", sa.String(length=255), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("auth_provider", "auth_subject", name=op.f("uq_users_auth_provider_subject")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_key", sa.String(length=50), nullable=False),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"], name=op.f("fk_user_roles_granted_by_user_id_users")
        ),
        sa.ForeignKeyConstraint(["role_key"], ["roles.key"], name=op.f("fk_user_roles_role_key_roles")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_roles_user_id_users")),
        sa.PrimaryKeyConstraint("user_id", "role_key", name=op.f("pk_user_roles")),
    )
    # The two roles the code itself knows about (domain/identity.py SYSTEM_ROLES). Approver roles are
    # added later: from the catalog (S15) and, in development, by the dev seed.
    now = datetime.now(UTC)
    op.bulk_insert(
        roles,
        [
            {
                "key": key,
                "label": label,
                "source": "system",
                "active": True,
                "created_at": now,
                "updated_at": now,
            }
            for key, label in (("admin", "Administrator"), ("viewer", "Viewer"))
        ],
    )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
