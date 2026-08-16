"""G08 durable object reconciliation audit runs.

Revision ID: ad9d3a5d7be1
Revises: 2e65c21b1887
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ad9d3a5d7be1"
down_revision: str | None = "2e65c21b1887"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "object_reconciliation_runs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(26),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'succeeded_with_alerts', 'failed')",
            name="valid_status",
        ),
    )
    op.create_index(
        "ix_object_reconciliation_runs_org_created",
        "object_reconciliation_runs",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_object_reconciliation_runs_org_created",
        table_name="object_reconciliation_runs",
    )
    op.drop_table("object_reconciliation_runs")
