"""Persist generated visual-style alternatives in planning jobs.

Revision ID: f25a7d1c9e40
Revises: e14a6c8d2f07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f25a7d1c9e40"
down_revision: str | Sequence[str] | None = "e14a6c8d2f07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "planning_jobs",
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        op.f("ck_planning_jobs_valid_operation"),
        "planning_jobs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_planning_jobs_valid_operation"),
        "planning_jobs",
        "operation IN ('intent_infer', 'outline_generate', 'visual_style_generate')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_planning_jobs_valid_operation"),
        "planning_jobs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_planning_jobs_valid_operation"),
        "planning_jobs",
        "operation IN ('intent_infer', 'outline_generate')",
    )
    op.drop_column("planning_jobs", "result_payload")
