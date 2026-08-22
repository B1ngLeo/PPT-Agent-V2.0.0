"""Persist Main Presentation Agent turns and tool observations.

Revision ID: b71c4e2f9a03
Revises: 9c0e3f6a4b12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b71c4e2f9a03"
down_revision: str | None = "9c0e3f6a4b12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_agent_turns",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=26), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("phase_id", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_model", sa.String(length=160), nullable=True),
        sa.Column("model_version", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=160), nullable=False),
        sa.Column("reference_version", sa.String(length=160), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_sha256", sa.String(length=64), nullable=True),
        sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observation_sha256", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_microunits", sa.BigInteger(), nullable=False),
        sa.Column("elapsed_seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "cost_microunits >= 0",
            name=op.f("ck_workflow_agent_turns_cost_nonnegative"),
        ),
        sa.CheckConstraint(
            "elapsed_seconds >= 0",
            name=op.f("ck_workflow_agent_turns_elapsed_nonnegative"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0",
            name=op.f("ck_workflow_agent_turns_input_tokens_nonnegative"),
        ),
        sa.CheckConstraint(
            "output_tokens >= 0",
            name=op.f("ck_workflow_agent_turns_output_tokens_nonnegative"),
        ),
        sa.CheckConstraint(
            "role IN ('strategist', 'executor')",
            name=op.f("ck_workflow_agent_turns_valid_role"),
        ),
        sa.CheckConstraint("sequence >= 1", name=op.f("ck_workflow_agent_turns_sequence_positive")),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            name=op.f("fk_workflow_agent_turns_run_org"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_agent_turns")),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            name=op.f("uq_workflow_agent_turns_id_org"),
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "sequence",
            name=op.f("uq_workflow_agent_turns_run_sequence"),
        ),
    )
    op.create_index(
        "ix_workflow_agent_turns_run_phase",
        "workflow_agent_turns",
        ["workflow_run_id", "phase_id"],
        unique=False,
    )
    op.create_table(
        "workflow_agent_tool_calls",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=26), nullable=False),
        sa.Column("agent_turn_id", sa.String(length=26), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("current_pnn", sa.String(length=8), nullable=True),
        sa.Column("author_attempt", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("arguments_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=False),
        sa.Column("subject_sha256", sa.String(length=64), nullable=False),
        sa.Column("observation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stale", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_version", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=160), nullable=False),
        sa.Column("reference_version", sa.String(length=160), nullable=False),
        sa.Column("usage_before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "author_attempt BETWEEN 1 AND 5",
            name=op.f("ck_workflow_agent_tool_calls_author_attempt_bounded"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_turn_id", "organization_id"],
            ["workflow_agent_turns.id", "workflow_agent_turns.organization_id"],
            name=op.f("fk_workflow_agent_tool_calls_turn_org"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            name=op.f("fk_workflow_agent_tool_calls_run_org"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_agent_tool_calls")),
    )
    op.create_index(
        "ix_workflow_agent_tool_calls_run_stage",
        "workflow_agent_tool_calls",
        ["workflow_run_id", "stage"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_agent_tool_calls_turn",
        "workflow_agent_tool_calls",
        ["agent_turn_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_agent_tool_calls_turn", table_name="workflow_agent_tool_calls")
    op.drop_index(
        "ix_workflow_agent_tool_calls_run_stage",
        table_name="workflow_agent_tool_calls",
    )
    op.drop_table("workflow_agent_tool_calls")
    op.drop_index("ix_workflow_agent_turns_run_phase", table_name="workflow_agent_turns")
    op.drop_table("workflow_agent_turns")
