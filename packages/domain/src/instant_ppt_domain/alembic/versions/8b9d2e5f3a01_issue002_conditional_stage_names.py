"""Add explicit image-resource, visual-review, and narration workflow stages.

Revision ID: 8b9d2e5f3a01
Revises: 7a8c1d4e2f90
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8b9d2e5f3a01"
down_revision: str | None = "7a8c1d4e2f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_STAGES = (
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
_CONDITIONAL_STAGES = (
    *_BASE_STAGES[:-5],
    "visual_review",
    *_BASE_STAGES[-5:-1],
    "narration",
    "publish",
)
_TABLES = (
    "workflow_runs",
    "workflow_stage_attempts",
    "workflow_checkpoint_sets",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_stage_checks(values: tuple[str, ...]) -> None:
    for table in _TABLES:
        op.drop_constraint(op.f(f"ck_{table}_valid_stage"), table, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_valid_stage"),
            table,
            f"stage IN ({_values(values)})",
        )


def upgrade() -> None:
    _replace_stage_checks(_CONDITIONAL_STAGES)


def downgrade() -> None:
    _replace_stage_checks(_BASE_STAGES)
