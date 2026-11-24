"""Baseline: app_meta, with this installation's ID.

Revision ID: 0001_baseline
Revises:
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    app_meta = op.create_table(
        "app_meta",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_meta")),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        app_meta,
        [{"key": "install_id", "value": str(uuid.uuid4()), "created_at": now, "updated_at": now}],
    )


def downgrade() -> None:
    op.drop_table("app_meta")
