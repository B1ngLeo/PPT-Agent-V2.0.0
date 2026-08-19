"""Bind ordered edit patches to effective presentation revisions.

Revision ID: 7a8c1d4e2f90
Revises: 6f4f2b3c9a10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a8c1d4e2f90"
down_revision: str | None = "6f4f2b3c9a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_effective_design_spec_revisions_presentation_revision",
        "effective_design_spec_revisions",
        ["presentation_revision_id"],
    )
    op.add_column(
        "design_spec_edit_patches",
        sa.Column("effective_spec_revision_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "design_spec_edit_patches",
        sa.Column("sequence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "design_spec_edit_patches",
        sa.Column("new_value_sha256", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY base_effective_spec_revision_id ORDER BY created_at, id
                   ) AS patch_sequence
            FROM design_spec_edit_patches
        )
        UPDATE design_spec_edit_patches AS patch
        SET effective_spec_revision_id = patch.base_effective_spec_revision_id,
            sequence = ranked.patch_sequence,
            new_value_sha256 = md5(patch.new_value::text) || md5(patch.new_value::text)
        FROM ranked
        WHERE ranked.id = patch.id
        """
    )
    op.alter_column("design_spec_edit_patches", "effective_spec_revision_id", nullable=False)
    op.alter_column("design_spec_edit_patches", "sequence", nullable=False)
    op.alter_column("design_spec_edit_patches", "new_value_sha256", nullable=False)
    op.create_foreign_key(
        "fk_design_spec_edit_patches_effective_revision",
        "design_spec_edit_patches",
        "effective_design_spec_revisions",
        ["effective_spec_revision_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_design_spec_edit_patches_revision_sequence",
        "design_spec_edit_patches",
        ["effective_spec_revision_id", "sequence"],
    )
    op.create_check_constraint(
        op.f("ck_design_spec_edit_patches_sequence_positive"),
        "design_spec_edit_patches",
        "sequence >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_design_spec_edit_patches_sequence_positive"),
        "design_spec_edit_patches",
        type_="check",
    )
    op.drop_constraint(
        "uq_design_spec_edit_patches_revision_sequence",
        "design_spec_edit_patches",
        type_="unique",
    )
    op.drop_constraint(
        "fk_design_spec_edit_patches_effective_revision",
        "design_spec_edit_patches",
        type_="foreignkey",
    )
    op.drop_column("design_spec_edit_patches", "new_value_sha256")
    op.drop_column("design_spec_edit_patches", "sequence")
    op.drop_column("design_spec_edit_patches", "effective_spec_revision_id")
    op.drop_constraint(
        "uq_effective_design_spec_revisions_presentation_revision",
        "effective_design_spec_revisions",
        type_="unique",
    )
