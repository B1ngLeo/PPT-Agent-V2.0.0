"""Add ISSUE-004 design-confirmation workflow states.

Revision ID: e14a6c8d2f07
Revises: d93f4a7b1c05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e14a6c8d2f07"
down_revision: str | Sequence[str] | None = "d93f4a7b1c05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_STATUSES = (
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
_NEW_STATUSES = (
    *_OLD_STATUSES[:5],
    "awaiting_design_confirmation",
    "design_confirmed",
    *_OLD_STATUSES[5:],
)
_OLD_STAGES = (
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
    "visual_review",
    "step7_finalize",
    "step7_export",
    "postflight",
    "pptx_content_gate",
    "narration",
    "publish",
)
_NEW_STAGES = (
    *_OLD_STAGES[:6],
    "strategizing",
    "awaiting_design_confirmation",
    "design_confirmed",
    *_OLD_STAGES[6:10],
    "spec_locked",
    *_OLD_STAGES[10:12],
    "executing",
    *_OLD_STAGES[12:15],
    "deck_qa",
    *_OLD_STAGES[15:23],
    "compiling",
    *_OLD_STAGES[23:],
    "published",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace(name: str, column: str, values: tuple[str, ...]) -> None:
    constraint_name = op.f(name)
    op.drop_constraint(constraint_name, "workflow_runs", type_="check")
    op.create_check_constraint(
        constraint_name, "workflow_runs", f"{column} IN ({_values(values)})"
    )


def upgrade() -> None:
    _replace("ck_workflow_runs_valid_status", "status", _NEW_STATUSES)
    _replace("ck_workflow_runs_valid_stage", "stage", _NEW_STAGES)


def downgrade() -> None:
    op.execute(
        "UPDATE workflow_runs SET status='running' "
        "WHERE status IN ('awaiting_design_confirmation','design_confirmed')"
    )
    op.execute(
        "UPDATE workflow_runs SET stage='design_spec_gate1' "
        "WHERE stage IN ('strategizing','awaiting_design_confirmation','design_confirmed')"
    )
    op.execute("UPDATE workflow_runs SET stage='spec_lock_gate2' WHERE stage='spec_locked'")
    op.execute("UPDATE workflow_runs SET stage='executor_p01' WHERE stage='executing'")
    op.execute("UPDATE workflow_runs SET stage='final_svg_gate' WHERE stage='deck_qa'")
    op.execute("UPDATE workflow_runs SET stage='step7_export' WHERE stage='compiling'")
    op.execute("UPDATE workflow_runs SET stage='publish' WHERE stage='published'")
    _replace("ck_workflow_runs_valid_status", "status", _OLD_STATUSES)
    _replace("ck_workflow_runs_valid_stage", "stage", _OLD_STAGES)
