"""Add the explicitly disclosed deterministic-template authoring profile.

Revision ID: c82d5f1a7b04
Revises: b71c4e2f9a03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c82d5f1a7b04"
down_revision: str | None = "b71c4e2f9a03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_workflow_runs_valid_profile"),
        "workflow_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_workflow_runs_valid_profile"),
        "workflow_runs",
        "profile IN ('default-agentic', 'deterministic-template', 'quick-engineering')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_workflow_runs_valid_profile"),
        "workflow_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_workflow_runs_valid_profile"),
        "workflow_runs",
        "profile IN ('default-agentic', 'quick-engineering')",
    )
