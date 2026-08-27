"""Persist asynchronous intent and outline planning jobs.

Revision ID: d93f4a7b1c05
Revises: c82d5f1a7b04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d93f4a7b1c05"
down_revision: str | Sequence[str] | None = "c82d5f1a7b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planning_jobs",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("draft_id", sa.String(length=26), nullable=False),
        sa.Column("actor_id", sa.String(length=26), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("base_revision_id", sa.String(length=26), nullable=True),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("result_revision_id", sa.String(length=26), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("request_id", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('intent_infer', 'outline_generate')",
            name=op.f("ck_planning_jobs_valid_operation"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'retrying', 'succeeded', 'failed')",
            name=op.f("ck_planning_jobs_valid_status"),
        ),
        sa.CheckConstraint(
            "attempt BETWEEN 0 AND max_attempts",
            name=op.f("ck_planning_jobs_attempt_bounded"),
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 5",
            name=op.f("ck_planning_jobs_max_attempts_bounded"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_planning_jobs_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            name="fk_planning_jobs_draft_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planning_jobs")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_planning_jobs_id_organization"
        ),
    )
    op.create_index(
        "ix_planning_jobs_draft_created",
        "planning_jobs",
        ["draft_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_planning_jobs_org_status",
        "planning_jobs",
        ["organization_id", "status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_planning_jobs_org_status", table_name="planning_jobs")
    op.drop_index("ix_planning_jobs_draft_created", table_name="planning_jobs")
    op.drop_table("planning_jobs")
