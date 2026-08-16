"""G07 editor export and history closure.

Revision ID: 2e65c21b1887
Revises: 16bafe0db753
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2e65c21b1887"
down_revision: str | None = "16bafe0db753"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "presentation_revisions", sa.Column("based_on_revision_id", sa.String(26))
    )
    op.add_column("presentation_revisions", sa.Column("actor_id", sa.String(26)))
    op.add_column(
        "presentation_revisions",
        sa.Column("accepted_missing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("slide_versions", sa.Column("source_slide_version_id", sa.String(26)))

    op.create_table(
        "slide_regeneration_jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("presentation_id", sa.String(26), nullable=False),
        sa.Column("base_revision_id", sa.String(26), nullable=False),
        sa.Column("slide_id", sa.String(26), nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("instruction", sa.String(2000), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_revision_id", sa.String(26)),
        sa.Column("result_artifact_id", sa.String(26)),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["presentation_id", "organization_id"],
            ["presentations.id", "presentations.organization_id"],
            name="fk_slide_regeneration_jobs_presentation_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["base_revision_id", "organization_id"],
            ["presentation_revisions.id", "presentation_revisions.organization_id"],
            name="fk_slide_regeneration_jobs_revision_org",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_slide_regeneration_jobs_id_org"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="valid_status",
        ),
    )
    op.create_index(
        "ix_slide_regeneration_jobs_presentation",
        "slide_regeneration_jobs",
        ["presentation_id", "created_at"],
    )

    op.create_table(
        "export_jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("presentation_id", sa.String(26), nullable=False),
        sa.Column("presentation_revision_id", sa.String(26), nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(16), nullable=False, server_default="queued"),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("options_sha256", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifact_id", sa.String(26)),
        sa.Column("manifest_artifact_id", sa.String(26)),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["presentation_id", "organization_id"],
            ["presentations.id", "presentations.organization_id"],
            name="fk_export_jobs_presentation_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_revision_id", "organization_id"],
            ["presentation_revisions.id", "presentation_revisions.organization_id"],
            name="fk_export_jobs_revision_org",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_export_jobs_id_org"),
        sa.UniqueConstraint(
            "presentation_revision_id",
            "options_sha256",
            name="uq_export_jobs_revision_options",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="valid_status",
        ),
        sa.CheckConstraint(
            "stage IN ('queued', 'compiling', 'package_qa', 'publishing')",
            name="valid_stage",
        ),
    )
    op.create_index(
        "ix_export_jobs_presentation_created",
        "export_jobs",
        ["presentation_id", "created_at"],
    )

    op.create_table(
        "data_exports",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("draft_id", sa.String(26), nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_id", sa.String(26)),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            name="fk_data_exports_draft_org",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_data_exports_id_org"),
        sa.UniqueConstraint("draft_id", "snapshot_sha256", name="uq_data_exports_snapshot"),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name="valid_status"
        ),
    )

    op.create_table(
        "project_cleanup_jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("organization_id", sa.String(26), nullable=False),
        sa.Column("draft_id", sa.String(26), nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
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
        sa.ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            name="fk_project_cleanup_jobs_draft_org",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("draft_id", name="uq_project_cleanup_jobs_draft"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="valid_status",
        ),
    )

    op.execute(
        """
        CREATE TRIGGER trg_data_exports_immutable
        BEFORE UPDATE OR DELETE ON data_exports
        FOR EACH ROW EXECUTE FUNCTION instant_ppt_reject_immutable_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_data_exports_immutable ON data_exports")
    op.drop_table("project_cleanup_jobs")
    op.drop_table("data_exports")
    op.drop_index("ix_export_jobs_presentation_created", table_name="export_jobs")
    op.drop_table("export_jobs")
    op.drop_index(
        "ix_slide_regeneration_jobs_presentation", table_name="slide_regeneration_jobs"
    )
    op.drop_table("slide_regeneration_jobs")
    op.drop_column("slide_versions", "source_slide_version_id")
    op.drop_column("presentation_revisions", "accepted_missing")
    op.drop_column("presentation_revisions", "actor_id")
    op.drop_column("presentation_revisions", "based_on_revision_id")
