"""g06 generation publication presentations

Revision ID: 16bafe0db753
Revises: 925b69af0f8f
Create Date: 2026-08-16 15:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "16bafe0db753"
down_revision: str | Sequence[str] | None = "925b69af0f8f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_artifacts",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("artifact_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("slide_id", sa.String(length=26), nullable=True),
        sa.Column("publication_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "publication_version >= 1",
            name=op.f("ck_generation_artifacts_publication_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            name="fk_generation_artifacts_artifact_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            name="fk_generation_artifacts_job_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_artifacts")),
        sa.UniqueConstraint("artifact_id", name="uq_generation_artifacts_artifact"),
    )
    op.create_index(
        "ix_generation_artifacts_job_kind",
        "generation_artifacts",
        ["job_id", "kind"],
        unique=False,
    )
    op.create_table(
        "generation_publications",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("manifest_artifact_id", sa.String(length=26), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_generation_publications_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            name="fk_generation_publications_job_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            name="fk_generation_publications_manifest_org",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_publications")),
        sa.UniqueConstraint("job_id", "version", name="uq_generation_publications_job_version"),
        sa.UniqueConstraint("manifest_artifact_id", name="uq_generation_publications_manifest"),
    )
    op.create_table(
        "presentations",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("draft_id", sa.String(length=26), nullable=False),
        sa.Column("generation_job_id", sa.String(length=26), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_revision_id", sa.String(length=26), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('ready', 'partial')", name=op.f("ck_presentations_valid_status")
        ),
        sa.ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            name="fk_presentations_draft_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["generation_job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            name="fk_presentations_job_org",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presentations")),
        sa.UniqueConstraint("generation_job_id", name="uq_presentations_generation_job"),
        sa.UniqueConstraint("id", "organization_id", name="uq_presentations_id_organization"),
    )
    op.create_index(
        "ix_presentations_org_updated",
        "presentations",
        ["organization_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "presentation_revisions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("presentation_id", sa.String(length=26), nullable=False),
        sa.Column("generation_job_id", sa.String(length=26), nullable=False),
        sa.Column("snapshot_id", sa.String(length=26), nullable=False),
        sa.Column("manifest_artifact_id", sa.String(length=26), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name=op.f("ck_presentation_revisions_revision_number_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["generation_job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            name="fk_presentation_revisions_job_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            name="fk_presentation_revisions_manifest_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id", "organization_id"],
            ["presentations.id", "presentations.organization_id"],
            name="fk_presentation_revisions_presentation_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presentation_revisions")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_presentation_revisions_id_organization"
        ),
        sa.UniqueConstraint(
            "presentation_id", "revision_number", name="uq_presentation_revisions_number"
        ),
    )
    op.create_index(
        "ix_presentation_revisions_presentation",
        "presentation_revisions",
        ["presentation_id", "revision_number"],
        unique=False,
    )
    op.create_table(
        "slide_versions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("organization_id", sa.String(length=26), nullable=False),
        sa.Column("presentation_revision_id", sa.String(length=26), nullable=False),
        sa.Column("slide_id", sa.String(length=26), nullable=False),
        sa.Column("outline_slide_id", sa.String(length=26), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_id", sa.String(length=26), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'failed')", name=op.f("ck_slide_versions_valid_status")
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_slide_versions_position_positive")),
        sa.ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            name="fk_slide_versions_artifact_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_revision_id", "organization_id"],
            ["presentation_revisions.id", "presentation_revisions.organization_id"],
            name="fk_slide_versions_revision_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slide_versions")),
        sa.UniqueConstraint(
            "presentation_revision_id",
            "position",
            name="uq_slide_versions_revision_position",
        ),
        sa.UniqueConstraint(
            "presentation_revision_id",
            "slide_id",
            name="uq_slide_versions_revision_slide",
        ),
    )
    op.add_column(
        "generation_job_slides",
        sa.Column("outline_slide_id", sa.String(length=26), nullable=True),
    )
    op.add_column("generation_job_slides", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column(
        "generation_job_slides",
        sa.Column(
            "body",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("generation_job_slides", "body", server_default=None)
    op.add_column(
        "generation_job_slides",
        sa.Column("render_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "generation_job_slides",
        sa.Column(
            "qa_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("generation_job_slides", "qa_report", server_default=None)
    op.add_column(
        "generation_jobs",
        sa.Column("processor", sa.String(length=16), server_default="fake", nullable=False),
    )
    op.alter_column("generation_jobs", "processor", server_default=None)
    op.add_column(
        "generation_jobs",
        sa.Column("publication_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("generation_jobs", "publication_version", server_default=None)
    op.create_check_constraint(
        op.f("ck_generation_jobs_valid_processor"),
        "generation_jobs",
        "processor IN ('fake', 'real')",
    )
    op.add_column(
        "generation_snapshots", sa.Column("approval_id", sa.String(length=26), nullable=True)
    )
    op.drop_constraint(op.f("ck_drafts_valid_status"), "drafts", type_="check")
    op.create_check_constraint(
        op.f("ck_drafts_valid_status"),
        "drafts",
        "status IN ('draft', 'outline_ready', 'approved', 'generating', "
        "'needs_attention', 'completed', 'failed', 'cancelled', 'deleted')",
    )
    for table_name in (
        "generation_snapshots",
        "generation_artifacts",
        "generation_publications",
        "presentation_revisions",
        "slide_versions",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION instant_ppt_reject_immutable_mutation()
            """
        )
    op.execute(
        """
        CREATE FUNCTION instant_ppt_guard_published_artifact()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND OLD.status = 'published' THEN
            RAISE EXCEPTION 'published artifact metadata cannot be deleted';
          END IF;
          IF TG_OP = 'UPDATE' AND OLD.status = 'published' AND (
            NEW.organization_id IS DISTINCT FROM OLD.organization_id OR
            NEW.artifact_type IS DISTINCT FROM OLD.artifact_type OR
            NEW.partition IS DISTINCT FROM OLD.partition OR
            NEW.object_key IS DISTINCT FROM OLD.object_key OR
            NEW.sha256 IS DISTINCT FROM OLD.sha256 OR
            NEW.media_type IS DISTINCT FROM OLD.media_type OR
            NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
          ) THEN
            RAISE EXCEPTION 'published artifact identity cannot be changed';
          END IF;
          RETURN COALESCE(NEW, OLD);
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_artifacts_published_identity
        BEFORE UPDATE OR DELETE ON artifacts
        FOR EACH ROW EXECUTE FUNCTION instant_ppt_guard_published_artifact()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_artifacts_published_identity ON artifacts")
    op.execute("DROP FUNCTION IF EXISTS instant_ppt_guard_published_artifact()")
    for table_name in (
        "generation_snapshots",
        "generation_artifacts",
        "generation_publications",
        "presentation_revisions",
        "slide_versions",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
    op.drop_constraint(op.f("ck_drafts_valid_status"), "drafts", type_="check")
    op.create_check_constraint(
        op.f("ck_drafts_valid_status"),
        "drafts",
        "status IN ('draft', 'outline_ready', 'approved', 'deleted')",
    )
    op.drop_column("generation_snapshots", "approval_id")
    op.drop_constraint(op.f("ck_generation_jobs_valid_processor"), "generation_jobs", type_="check")
    op.drop_column("generation_jobs", "publication_version")
    op.drop_column("generation_jobs", "processor")
    op.drop_column("generation_job_slides", "qa_report")
    op.drop_column("generation_job_slides", "render_sha256")
    op.drop_column("generation_job_slides", "body")
    op.drop_column("generation_job_slides", "title")
    op.drop_column("generation_job_slides", "outline_slide_id")
    op.drop_table("slide_versions")
    op.drop_index("ix_presentation_revisions_presentation", table_name="presentation_revisions")
    op.drop_table("presentation_revisions")
    op.drop_index("ix_presentations_org_updated", table_name="presentations")
    op.drop_table("presentations")
    op.drop_table("generation_publications")
    op.drop_index("ix_generation_artifacts_job_kind", table_name="generation_artifacts")
    op.drop_table("generation_artifacts")
