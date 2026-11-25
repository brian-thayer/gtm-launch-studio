"""Audit events: the append-only trail of state changes.

Revision ID: 0003_audit_events
Revises: 0002_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_audit_events"
down_revision: str | None = "0002_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY = "audit_events is append-only"


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_display", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("before_hash", sa.String(length=64), nullable=True),
        sa.Column("after_hash", sa.String(length=64), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_events_actor_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_entity_type_entity_id", "audit_events", ["entity_type", "entity_id"], unique=False
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"], unique=False)
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"], unique=False)

    # Append-only. SQLite has no GRANT, so triggers refuse any UPDATE or DELETE of a row. On Postgres the
    # application's database role gets `REVOKE UPDATE, DELETE ON audit_events` instead (docs/hosting.md,
    # S09), which is why nothing is created for other dialects here.
    if op.get_bind().dialect.name == "sqlite":
        for verb in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER audit_events_no_{verb.lower()} BEFORE {verb} ON audit_events "
                f"BEGIN SELECT RAISE(ABORT, '{_APPEND_ONLY}'); END"
            )


def downgrade() -> None:
    # DROP TABLE removes its triggers too; dropping them first only keeps the intent explicit.
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_entity_type_entity_id", table_name="audit_events")
    op.drop_table("audit_events")
