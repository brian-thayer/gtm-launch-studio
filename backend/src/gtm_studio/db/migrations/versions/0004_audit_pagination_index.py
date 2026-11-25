"""Audit events: index keyset pagination's sort key, ``(occurred_at, id)`` (ADR-0006).

It replaces the single-column ``occurred_at`` index. Only indexes change: no rows are touched and the
append-only triggers stay as they are.

Revision ID: 0004_audit_pagination_index
Revises: 0003_audit_events
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_audit_pagination_index"
down_revision: str | None = "0003_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_audit_events_occurred_at_id", "audit_events", ["occurred_at", "id"], unique=False)
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")


def downgrade() -> None:
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"], unique=False)
    op.drop_index("ix_audit_events_occurred_at_id", table_name="audit_events")
