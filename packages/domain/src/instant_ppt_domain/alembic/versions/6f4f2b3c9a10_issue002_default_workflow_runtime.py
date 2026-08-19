"""ISSUE-002 Default Agentic workflow runtime and effective spec revisions.

Revision ID: 6f4f2b3c9a10
Revises: ad9d3a5d7be1
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6f4f2b3c9a10"
down_revision: str | None = "ad9d3a5d7be1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKFLOW_STATUSES = (
    "created",
    "running",
    "awaiting_stage1_confirmation",
    "template_handoff_ready",
    "awaiting_stage2_confirmation",
    "final_confirmed",
    "awaiting_refine_spec_approval",
    "needs_manual",
    "partially_succeeded",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
)
WORKFLOW_STAGES = (
    "attribution_guard",
    "source_import",
    "template_candidates",
    "stage1",
    "template_handoff",
    "stage2",
    "image_resources",
    "design_spec_gate1",
    "refine_spec",
    "spec_lock_gate2",
    "design_parameters",
    "live_preview",
    "executor_p01",
    "first_page_gate",
    "executor_remaining",
    "final_svg_gate",
    "chart_gate",
    "final_svg_content_gate",
    "notes",
    "animations",
    "step7_finalize",
    "step7_export",
    "postflight",
    "pptx_content_gate",
    "publish",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("generation_job_id", sa.String(26), nullable=False),
        sa.Column("snapshot_id", sa.String(26), nullable=False),
        sa.Column("route", sa.String(40), nullable=False),
        sa.Column("profile", sa.String(40), nullable=False),
        sa.Column("workflow_version", sa.String(80), nullable=False),
        sa.Column("engine_version", sa.String(80), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("approved_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.String(26)),
        sa.Column("lease_owner", sa.String(160)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("current_checkpoint_set_id", sa.String(26)),
        sa.Column("runtime_policy", postgresql.JSONB(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False),
        sa.Column("error", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["generation_job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_runs_generation_job_org",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "organization_id"],
            ["generation_snapshots.id", "generation_snapshots.organization_id"],
            ondelete="RESTRICT",
            name="fk_workflow_runs_snapshot_org",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_workflow_runs_id_organization"),
        sa.UniqueConstraint("generation_job_id", name="uq_workflow_runs_generation_job"),
        sa.UniqueConstraint("request_sha256", name="uq_workflow_runs_request_sha256"),
        sa.CheckConstraint(f"status IN ({_values(WORKFLOW_STATUSES)})", name="valid_status"),
        sa.CheckConstraint(f"stage IN ({_values(WORKFLOW_STAGES)})", name="valid_stage"),
        sa.CheckConstraint("route = 'generate_pptx'", name="valid_route"),
        sa.CheckConstraint(
            "profile IN ('default-agentic', 'quick-engineering')", name="valid_profile"
        ),
        sa.CheckConstraint("attempt BETWEEN 0 AND max_attempts", name="attempt_bounded"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 5", name="max_attempts_bounded"),
    )
    op.create_index(
        "ix_workflow_runs_org_created", "workflow_runs", ["organization_id", "created_at"]
    )

    op.create_table(
        "workflow_stage_attempts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("workflow_run_id", sa.String(26), nullable=False),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("fencing_token", sa.String(26), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("output_sha256", sa.String(64)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_detail", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_stage_attempts_run_org",
        ),
        sa.UniqueConstraint(
            "workflow_run_id", "stage", "attempt", name="uq_workflow_stage_attempts_run_stage"
        ),
        sa.CheckConstraint(f"stage IN ({_values(WORKFLOW_STAGES)})", name="valid_stage"),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'cancelled')", name="valid_status"
        ),
        sa.CheckConstraint("attempt BETWEEN 1 AND 5", name="attempt_bounded"),
    )
    op.create_index(
        "ix_workflow_stage_attempts_run_created",
        "workflow_stage_attempts",
        ["workflow_run_id", "created_at"],
    )

    op.create_table(
        "workflow_checkpoint_sets",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("workflow_run_id", sa.String(26), nullable=False),
        sa.Column("stage_attempt_id", sa.String(26), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("output_sha256", sa.String(64), nullable=False),
        sa.Column("checkpoint_sha256", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_checkpoint_sets_run_org",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_workflow_checkpoint_sets_id_org"),
        sa.UniqueConstraint(
            "workflow_run_id", "sequence", name="uq_workflow_checkpoint_sets_run_sequence"
        ),
        sa.UniqueConstraint(
            "checkpoint_sha256", name="uq_workflow_checkpoint_sets_checkpoint_sha256"
        ),
        sa.CheckConstraint(f"stage IN ({_values(WORKFLOW_STAGES)})", name="valid_stage"),
        sa.CheckConstraint("sequence >= 1", name="sequence_positive"),
    )
    op.create_index(
        "ix_workflow_checkpoint_sets_run_created",
        "workflow_checkpoint_sets",
        ["workflow_run_id", "created_at"],
    )

    op.create_table(
        "workflow_gate_receipts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("workflow_run_id", sa.String(26), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("subject_sha256", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(26)),
        sa.Column("delegated", sa.Boolean(), nullable=False),
        sa.Column("delegation_scope", postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_gate_receipts_run_org",
        ),
        sa.UniqueConstraint("receipt_sha256", name="uq_workflow_gate_receipts_sha256"),
        sa.CheckConstraint(
            "status IN ('pending', 'passed', 'passed-with-warnings', 'failed', 'stale')",
            name="valid_status",
        ),
    )
    op.create_index(
        "ix_workflow_gate_receipts_run_kind", "workflow_gate_receipts", ["workflow_run_id", "kind"]
    )

    op.create_table(
        "workflow_intermediate_artifacts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("workflow_run_id", sa.String(26), nullable=False),
        sa.Column("checkpoint_set_id", sa.String(26), nullable=False),
        sa.Column("artifact_id", sa.String(26), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("output_sha256", sa.String(64), nullable=False),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_intermediate_artifacts_run_org",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_workflow_intermediate_artifacts_artifact_org",
        ),
        sa.UniqueConstraint("artifact_id", name="uq_workflow_intermediate_artifacts_artifact"),
    )
    op.create_index(
        "ix_workflow_intermediate_artifacts_run_kind",
        "workflow_intermediate_artifacts",
        ["workflow_run_id", "kind"],
    )

    op.create_table(
        "effective_design_spec_revisions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("workflow_run_id", sa.String(26), nullable=False),
        sa.Column("presentation_revision_id", sa.String(26)),
        sa.Column("based_on_id", sa.String(26)),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("base_design_spec_sha256", sa.String(64), nullable=False),
        sa.Column("effective_spec_sha256", sa.String(64), nullable=False),
        sa.Column("spec_lock_sha256", sa.String(64), nullable=False),
        sa.Column("roster", postgresql.JSONB(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_effective_design_spec_revisions_run_org",
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_effective_design_spec_revisions_id_org"
        ),
        sa.UniqueConstraint(
            "workflow_run_id", "revision_number", name="uq_effective_design_spec_revisions_number"
        ),
        sa.UniqueConstraint(
            "effective_spec_sha256", name="uq_effective_design_spec_revisions_effective_spec_sha256"
        ),
        sa.CheckConstraint("revision_number >= 1", name="revision_number_positive"),
    )

    op.create_table(
        "design_spec_edit_patches",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("workflow_run_id", sa.String(26), nullable=False),
        sa.Column("base_effective_spec_revision_id", sa.String(26), nullable=False),
        sa.Column("slide_id", sa.String(26), nullable=False),
        sa.Column("object_key", sa.String(160), nullable=False),
        sa.Column("old_value_sha256", sa.String(64), nullable=False),
        sa.Column("new_value", postgresql.JSONB(), nullable=False),
        sa.Column("touches_lock_owned_field", sa.Boolean(), nullable=False),
        sa.Column("actor_id", sa.String(26), nullable=False),
        sa.Column("patch_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_design_spec_edit_patches_run_org",
        ),
        sa.UniqueConstraint("patch_sha256", name="uq_design_spec_edit_patches_sha256"),
    )
    op.create_index(
        "ix_design_spec_edit_patches_run_created",
        "design_spec_edit_patches",
        ["workflow_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_design_spec_edit_patches_run_created", table_name="design_spec_edit_patches")
    op.drop_table("design_spec_edit_patches")
    op.drop_table("effective_design_spec_revisions")
    op.drop_index(
        "ix_workflow_intermediate_artifacts_run_kind", table_name="workflow_intermediate_artifacts"
    )
    op.drop_table("workflow_intermediate_artifacts")
    op.drop_index("ix_workflow_gate_receipts_run_kind", table_name="workflow_gate_receipts")
    op.drop_table("workflow_gate_receipts")
    op.drop_index("ix_workflow_checkpoint_sets_run_created", table_name="workflow_checkpoint_sets")
    op.drop_table("workflow_checkpoint_sets")
    op.drop_index("ix_workflow_stage_attempts_run_created", table_name="workflow_stage_attempts")
    op.drop_table("workflow_stage_attempts")
    op.drop_index("ix_workflow_runs_org_created", table_name="workflow_runs")
    op.drop_table("workflow_runs")
