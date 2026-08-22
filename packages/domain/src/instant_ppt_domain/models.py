"""G02 PostgreSQL persistence model.

The schema deliberately keeps durable state, events, leases, idempotency, and
simulated publication records in PostgreSQL. Redis carries no authoritative
business state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ULID_LENGTH = 26
JOB_STATUSES = (
    "queued",
    "running",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "partially_succeeded",
    "failed",
)
JOB_STAGES = (
    "deck_planning",
    "slide_generation",
    "deck_qa",
    "compiling",
    "package_qa",
    "publishing",
)
SLIDE_STATUSES = ("pending", "running", "ready", "failed", "retrying", "cancelled")
SLIDE_STAGES = ("content_generation", "rendering", "qa")
ORGANIZATION_KINDS = ("synthetic", "personal", "team")
USER_STATUSES = ("active", "disabled")
MEMBERSHIP_ROLES = ("owner", "member")
MEMBERSHIP_STATUSES = ("active", "revoked")
ARTIFACT_PARTITIONS = ("quarantine", "clean", "tmp", "published")
ARTIFACT_STATUSES = ("pending", "published", "revoked", "deleted")
UPLOAD_SESSION_STATUSES = ("pending", "uploaded", "completed", "expired", "rejected")
SOURCE_STATUSES = (
    "upload_pending",
    "uploading",
    "uploaded",
    "scanning",
    "clean",
    "parsing",
    "parsed",
    "rejected",
    "parse_failed",
    "cancelled",
)
SCAN_STATUSES = ("pending", "running", "clean", "rejected", "failed")
PARSE_STATUSES = ("pending", "running", "succeeded", "failed")
SOURCE_ARTIFACT_KINDS = ("markdown", "asset", "conversion_profile")
DRAFT_STATUSES = (
    "draft",
    "outline_ready",
    "approved",
    "generating",
    "needs_attention",
    "completed",
    "failed",
    "cancelled",
    "deleted",
)
REVISION_ACTORS = ("user", "ai", "system")
PROVIDER_CALL_STATUSES = ("succeeded", "failed", "rate_limited", "timed_out")
WORKFLOW_RUN_STATUSES = (
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
    "visual_review",
    "step7_finalize",
    "step7_export",
    "postflight",
    "pptx_content_gate",
    "narration",
    "publish",
)
TERMINAL_JOB_STATUSES = frozenset({"cancelled", "succeeded", "partially_succeeded", "failed"})
TERMINAL_WORKFLOW_STATUSES = frozenset({"cancelled", "succeeded", "partially_succeeded", "failed"})


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
        CheckConstraint(f"status IN ({_values(USER_STATUSES)})", name="valid_status"),
        Index("ix_users_email_normalized", "email_normalized"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(320), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        UniqueConstraint("personal_owner_user_id", name="uq_organizations_personal_owner_user"),
        CheckConstraint(f"kind IN ({_values(ORGANIZATION_KINDS)})", name="valid_kind"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="synthetic")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    personal_owner_user_id: Mapped[str | None] = mapped_column(
        String(ULID_LENGTH), ForeignKey("users.id", ondelete="RESTRICT")
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ServiceActor(Base):
    __tablename__ = "service_actors"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_service_actors_id_organization"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_organization_user"),
        CheckConstraint(f"role IN ({_values(MEMBERSHIP_ROLES)})", name="valid_role"),
        CheckConstraint(f"status IN ({_values(MEMBERSHIP_STATUSES)})", name="valid_status"),
        Index("ix_memberships_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="owner")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class GenerationSnapshot(Base):
    __tablename__ = "generation_snapshots"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_generation_snapshots_id_organization"),
        UniqueConstraint(
            "organization_id", "snapshot_sha256", name="uq_generation_snapshots_org_sha"
        ),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    approval_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    intent_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    outline_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    template_version_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    mode_id: Mapped[str] = mapped_column(String(32), nullable=False, default="native")
    source_hashes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    container_version: Mapped[str] = mapped_column(String(160), nullable=False)
    font_pack_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["snapshot_id", "organization_id"],
            ["generation_snapshots.id", "generation_snapshots.organization_id"],
            ondelete="RESTRICT",
            name="fk_generation_jobs_snapshot_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_generation_jobs_id_organization"),
        CheckConstraint(f"status IN ({_values(JOB_STATUSES)})", name="valid_status"),
        CheckConstraint(f"stage IN ({_values(JOB_STAGES)})", name="valid_stage"),
        CheckConstraint("processor IN ('fake', 'real')", name="valid_processor"),
        CheckConstraint("latest_seq >= 0", name="latest_seq_nonnegative"),
        CheckConstraint("attempt >= 0", name="attempt_nonnegative"),
        Index("ix_generation_jobs_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    processor: Mapped[str] = mapped_column(String(16), nullable=False, default="fake")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="deck_planning")
    latest_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    publication_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_token: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    test_behavior: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class GenerationJobSlide(Base):
    __tablename__ = "generation_job_slides"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_generation_job_slides_job_org",
        ),
        UniqueConstraint("job_id", "position", name="uq_generation_job_slides_position"),
        UniqueConstraint("job_id", "slide_id", name="uq_generation_job_slides_slide"),
        CheckConstraint(f"status IN ({_values(SLIDE_STATUSES)})", name="valid_status"),
        CheckConstraint(f"stage IN ({_values(SLIDE_STAGES)})", name="valid_stage"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint("attempt >= 0", name="attempt_nonnegative"),
        CheckConstraint("max_attempts BETWEEN 1 AND 5", name="max_attempts_bounded"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    slide_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    outline_slide_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="content_generation")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    failure_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    logical_task_key: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(320))
    render_sha256: Mapped[str | None] = mapped_column(String(64))
    qa_report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_job_events_job_org",
        ),
        UniqueConstraint("job_id", "seq", name="uq_job_events_job_seq"),
        Index("ix_job_events_job_occurred", "job_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    slide_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    progress_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    trace_id: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("kind IN ('event', 'task')", name="valid_kind"),
        CheckConstraint("status IN ('pending', 'dispatched')", name="valid_status"),
        Index("ix_outbox_events_pending", "status", "available_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(360), nullable=False, unique=True)
    destination: Mapped[str] = mapped_column(String(320), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "actor_id",
            "route",
            "idempotency_key",
            name="uq_idempotency_records_scope",
        ),
        Index("ix_idempotency_records_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="service")
    route: Mapped[str] = mapped_column(String(320), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PublishedFixtureManifest(Base):
    __tablename__ = "published_fixture_manifests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_published_fixture_manifests_job_org",
        ),
        UniqueConstraint("job_id", name="uq_published_fixture_manifests_job"),
        UniqueConstraint("logical_task_key", name="uq_published_fixture_manifests_task"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    logical_task_key: Mapped[str] = mapped_column(String(320), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UsageReservation(Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_usage_reservations_job_org",
        ),
        UniqueConstraint("job_id", name="uq_usage_reservations_job"),
        CheckConstraint("status IN ('reserved', 'settled', 'released')", name="valid_status"),
        CheckConstraint("reserved_units >= 0", name="reserved_units_nonnegative"),
        CheckConstraint("settled_units >= 0", name="settled_units_nonnegative"),
        CheckConstraint("reserved_images >= 0", name="reserved_images_nonnegative"),
        CheckConstraint("settled_images >= 0", name="settled_images_nonnegative"),
        CheckConstraint(
            "reserved_cost_microunits >= 0", name="reserved_cost_microunits_nonnegative"
        ),
        CheckConstraint(
            "settled_cost_microunits >= 0", name="settled_cost_microunits_nonnegative"
        ),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    reserved_units: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settled_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_cost_microunits: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    settled_cost_microunits: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_entitlements_organization"),
        CheckConstraint("max_slides_per_deck BETWEEN 1 AND 100", name="slides_bounded"),
        CheckConstraint("monthly_slide_limit >= 0", name="monthly_slides_nonnegative"),
        CheckConstraint("max_images_per_deck BETWEEN 0 AND 32", name="images_bounded"),
        CheckConstraint("monthly_image_limit >= 0", name="monthly_images_nonnegative"),
        CheckConstraint(
            "monthly_image_cost_limit_microunits >= 0",
            name="monthly_image_cost_nonnegative",
        ),
        CheckConstraint("max_concurrent_jobs >= 1", name="concurrency_positive"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False, default="p1-default")
    max_slides_per_deck: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    monthly_slide_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    max_images_per_deck: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    monthly_image_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    monthly_image_cost_limit_microunits: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=3_000_000
    )
    max_concurrent_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    allowed_modes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UsageLedger(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        UniqueConstraint("organization_id", "dedupe_key", name="uq_usage_ledger_org_dedupe"),
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
        Index("ix_usage_ledger_org_occurred", "organization_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(320), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_artifacts_id_organization"),
        UniqueConstraint("object_key", name="uq_artifacts_object_key"),
        CheckConstraint(f"partition IN ({_values(ARTIFACT_PARTITIONS)})", name="valid_partition"),
        CheckConstraint(f"status IN ({_values(ARTIFACT_STATUSES)})", name="valid_status"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        Index("ix_artifacts_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    partition: Mapped[str] = mapped_column(String(16), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    retention_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ArtifactDownloadGrant(Base):
    __tablename__ = "artifact_download_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="CASCADE",
            name="fk_artifact_download_grants_artifact_org",
        ),
        Index("ix_artifact_download_grants_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_request", "request_id"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_sources_id_organization"),
        ForeignKeyConstraint(
            ["input_artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_sources_input_artifact_org",
        ),
        CheckConstraint(f"status IN ({_values(SOURCE_STATUSES)})", name="valid_status"),
        CheckConstraint(f"scan_status IN ({_values(SCAN_STATUSES)})", name="valid_scan_status"),
        CheckConstraint(f"parse_status IN ({_values(PARSE_STATUSES)})", name="valid_parse_status"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        CheckConstraint("scan_attempt BETWEEN 0 AND 5", name="scan_attempt_bounded"),
        CheckConstraint("parse_attempt BETWEEN 0 AND 5", name="parse_attempt_bounded"),
        Index("ix_sources_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_artifact_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(12), nullable=False)
    declared_mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    detected_mime_type: Mapped[str | None] = mapped_column(String(160))
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="upload_pending")
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    scan_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scan_decision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_package: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    parser_version: Mapped[str | None] = mapped_column(String(160))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_detail: Mapped[str | None] = mapped_column(String(1000))
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parse_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "organization_id"],
            ["sources.id", "sources.organization_id"],
            ondelete="CASCADE",
            name="fk_upload_sessions_source_org",
        ),
        UniqueConstraint("source_id", name="uq_upload_sessions_source"),
        UniqueConstraint("object_key", name="uq_upload_sessions_object_key"),
        CheckConstraint(f"status IN ({_values(UPLOAD_SESSION_STATUSES)})", name="valid_status"),
        CheckConstraint("expected_size_bytes >= 1", name="expected_size_positive"),
        CheckConstraint("max_bytes >= expected_size_bytes", name="max_covers_expected"),
        Index("ix_upload_sessions_org_expires", "organization_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    source_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    declared_mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "organization_id"],
            ["sources.id", "sources.organization_id"],
            ondelete="CASCADE",
            name="fk_source_artifacts_source_org",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_source_artifacts_artifact_org",
        ),
        UniqueConstraint("artifact_id", name="uq_source_artifacts_artifact"),
        CheckConstraint(f"kind IN ({_values(SOURCE_ARTIFACT_KINDS)})", name="valid_kind"),
        Index("ix_source_artifacts_source_kind", "source_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    source_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_templates_slug"),
        Index("ix_templates_catalog", "is_active", "category", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (
        UniqueConstraint("id", "template_id", name="uq_template_versions_id_template"),
        UniqueConstraint("template_id", "version", name="uq_template_versions_template_version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    template_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("templates.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="native")
    theme_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    page_roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    editable_elements: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    engine_compatibility: Mapped[str] = mapped_column(String(120), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_drafts_id_organization"),
        ForeignKeyConstraint(
            ["source_id", "organization_id"],
            ["sources.id", "sources.organization_id"],
            ondelete="RESTRICT",
            name="fk_drafts_source_org",
        ),
        CheckConstraint(f"status IN ({_values(DRAFT_STATUSES)})", name="valid_status"),
        CheckConstraint("mode = 'native'", name="native_mode_only"),
        CheckConstraint("lock_version >= 1", name="lock_version_positive"),
        Index("ix_drafts_org_updated", "organization_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    source_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="native")
    template_version_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    current_intent_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    current_outline_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    approved_outline_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            ondelete="CASCADE",
            name="fk_provider_calls_draft_org",
        ),
        CheckConstraint(f"status IN ({_values(PROVIDER_CALL_STATUSES)})", name="valid_status"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_nonnegative"),
        CheckConstraint("repair_count BETWEEN 0 AND 2", name="repair_count_bounded"),
        Index("ix_provider_calls_org_started", "organization_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IntentRevision(Base):
    __tablename__ = "intent_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            ondelete="CASCADE",
            name="fk_intent_revisions_draft_org",
        ),
        CheckConstraint(f"actor_kind IN ({_values(REVISION_ACTORS)})", name="valid_actor"),
        Index("ix_intent_revisions_draft_created", "draft_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    based_on_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    actor_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_call_id: Mapped[str | None] = mapped_column(
        String(ULID_LENGTH), ForeignKey("provider_calls.id", ondelete="SET NULL")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutlineRevision(Base):
    __tablename__ = "outline_revisions"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_outline_revisions_id_organization"),
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            ondelete="CASCADE",
            name="fk_outline_revisions_draft_org",
        ),
        CheckConstraint(f"actor_kind IN ({_values(REVISION_ACTORS)})", name="valid_actor"),
        CheckConstraint("target_slide_count BETWEEN 4 AND 30", name="target_slide_count_bounded"),
        Index("ix_outline_revisions_draft_created", "draft_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    based_on_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    actor_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_call_id: Mapped[str | None] = mapped_column(
        String(ULID_LENGTH), ForeignKey("provider_calls.id", ondelete="SET NULL")
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False, default="edit")
    story_summary: Mapped[str] = mapped_column(Text, nullable=False)
    target_slide_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutlineSlide(Base):
    __tablename__ = "outline_slides"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outline_revision_id", "organization_id"],
            ["outline_revisions.id", "outline_revisions.organization_id"],
            ondelete="CASCADE",
            name="fk_outline_slides_revision_org",
        ),
        UniqueConstraint(
            "outline_revision_id", "outline_slide_id", name="uq_outline_slides_revision_slide"
        ),
        UniqueConstraint(
            "outline_revision_id", "position", name="uq_outline_slides_revision_position"
        ),
        CheckConstraint("position >= 1", name="position_positive"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    outline_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    outline_slide_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    key_points: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    source_citations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutlineApproval(Base):
    __tablename__ = "outline_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            ondelete="CASCADE",
            name="fk_outline_approvals_draft_org",
        ),
        ForeignKeyConstraint(
            ["outline_revision_id", "organization_id"],
            ["outline_revisions.id", "outline_revisions.organization_id"],
            ondelete="RESTRICT",
            name="fk_outline_approvals_revision_org",
        ),
        UniqueConstraint("outline_revision_id", name="uq_outline_approvals_outline_revision"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    outline_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    intent_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    template_version_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    source_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GenerationArtifact(Base):
    __tablename__ = "generation_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_generation_artifacts_job_org",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_generation_artifacts_artifact_org",
        ),
        UniqueConstraint("artifact_id", name="uq_generation_artifacts_artifact"),
        CheckConstraint("publication_version >= 1", name="publication_version_positive"),
        Index("ix_generation_artifacts_job_kind", "job_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    slide_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    publication_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GenerationPublication(Base):
    __tablename__ = "generation_publications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_generation_publications_job_org",
        ),
        ForeignKeyConstraint(
            ["manifest_artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_generation_publications_manifest_org",
        ),
        UniqueConstraint("job_id", "version", name="uq_generation_publications_job_version"),
        UniqueConstraint("manifest_artifact_id", name="uq_generation_publications_manifest"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_artifact_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Presentation(Base):
    __tablename__ = "presentations"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_presentations_id_organization"),
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            ondelete="RESTRICT",
            name="fk_presentations_draft_org",
        ),
        ForeignKeyConstraint(
            ["generation_job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="RESTRICT",
            name="fk_presentations_job_org",
        ),
        UniqueConstraint("generation_job_id", name="uq_presentations_generation_job"),
        CheckConstraint("status IN ('ready', 'partial')", name="valid_status"),
        Index("ix_presentations_org_updated", "organization_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    generation_job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PresentationRevision(Base):
    __tablename__ = "presentation_revisions"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_presentation_revisions_id_organization"),
        ForeignKeyConstraint(
            ["presentation_id", "organization_id"],
            ["presentations.id", "presentations.organization_id"],
            ondelete="CASCADE",
            name="fk_presentation_revisions_presentation_org",
        ),
        ForeignKeyConstraint(
            ["generation_job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="RESTRICT",
            name="fk_presentation_revisions_job_org",
        ),
        ForeignKeyConstraint(
            ["manifest_artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_presentation_revisions_manifest_org",
        ),
        UniqueConstraint(
            "presentation_id", "revision_number", name="uq_presentation_revisions_number"
        ),
        CheckConstraint("revision_number >= 1", name="revision_number_positive"),
        Index("ix_presentation_revisions_presentation", "presentation_id", "revision_number"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    presentation_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    generation_job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    manifest_artifact_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    based_on_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    actor_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False, default="generation")
    partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepted_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SlideVersion(Base):
    __tablename__ = "slide_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["presentation_revision_id", "organization_id"],
            ["presentation_revisions.id", "presentation_revisions.organization_id"],
            ondelete="CASCADE",
            name="fk_slide_versions_revision_org",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_slide_versions_artifact_org",
        ),
        UniqueConstraint(
            "presentation_revision_id", "slide_id", name="uq_slide_versions_revision_slide"
        ),
        UniqueConstraint(
            "presentation_revision_id", "position", name="uq_slide_versions_revision_position"
        ),
        CheckConstraint("status IN ('ready', 'failed')", name="valid_status"),
        CheckConstraint("position >= 1", name="position_positive"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    presentation_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    slide_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    outline_slide_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    source_slide_version_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    error_code: Mapped[str | None] = mapped_column(String(80))
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SlideRegenerationJob(Base):
    __tablename__ = "slide_regeneration_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["presentation_id", "organization_id"],
            ["presentations.id", "presentations.organization_id"],
            ondelete="CASCADE",
            name="fk_slide_regeneration_jobs_presentation_org",
        ),
        ForeignKeyConstraint(
            ["base_revision_id", "organization_id"],
            ["presentation_revisions.id", "presentation_revisions.organization_id"],
            ondelete="RESTRICT",
            name="fk_slide_regeneration_jobs_revision_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_slide_regeneration_jobs_id_org"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="valid_status",
        ),
        Index("ix_slide_regeneration_jobs_presentation", "presentation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    presentation_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    base_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    slide_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    created_by: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    instruction: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    result_artifact_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["presentation_id", "organization_id"],
            ["presentations.id", "presentations.organization_id"],
            ondelete="CASCADE",
            name="fk_export_jobs_presentation_org",
        ),
        ForeignKeyConstraint(
            ["presentation_revision_id", "organization_id"],
            ["presentation_revisions.id", "presentation_revisions.organization_id"],
            ondelete="RESTRICT",
            name="fk_export_jobs_revision_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_export_jobs_id_org"),
        UniqueConstraint(
            "presentation_revision_id", "options_sha256", name="uq_export_jobs_revision_options"
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="valid_status",
        ),
        CheckConstraint(
            "stage IN ('queued', 'compiling', 'package_qa', 'publishing')",
            name="valid_stage",
        ),
        Index("ix_export_jobs_presentation_created", "presentation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    presentation_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    presentation_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    created_by: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    options_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifact_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    manifest_artifact_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_job_id", "organization_id"],
            ["generation_jobs.id", "generation_jobs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_runs_generation_job_org",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "organization_id"],
            ["generation_snapshots.id", "generation_snapshots.organization_id"],
            ondelete="RESTRICT",
            name="fk_workflow_runs_snapshot_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_workflow_runs_id_organization"),
        UniqueConstraint("generation_job_id", name="uq_workflow_runs_generation_job"),
        UniqueConstraint("request_sha256", name="uq_workflow_runs_request_sha256"),
        CheckConstraint(f"status IN ({_values(WORKFLOW_RUN_STATUSES)})", name="valid_status"),
        CheckConstraint(f"stage IN ({_values(WORKFLOW_STAGES)})", name="valid_stage"),
        CheckConstraint("route = 'generate_pptx'", name="valid_route"),
        CheckConstraint(
            "profile IN ('default-agentic', 'deterministic-template', 'quick-engineering')",
            name="valid_profile",
        ),
        CheckConstraint("attempt BETWEEN 0 AND max_attempts", name="attempt_bounded"),
        CheckConstraint("max_attempts BETWEEN 1 AND 5", name="max_attempts_bounded"),
        Index("ix_workflow_runs_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    generation_job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    route: Mapped[str] = mapped_column(String(40), nullable=False, default="generate_pptx")
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(80), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False, default="created")
    stage: Mapped[str] = mapped_column(String(48), nullable=False, default="attribution_guard")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    fencing_token: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_checkpoint_set_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    runtime_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowStageAttempt(Base):
    __tablename__ = "workflow_stage_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_stage_attempts_run_org",
        ),
        UniqueConstraint(
            "workflow_run_id", "stage", "attempt", name="uq_workflow_stage_attempts_run_stage"
        ),
        CheckConstraint(f"stage IN ({_values(WORKFLOW_STAGES)})", name="valid_stage"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'cancelled')", name="valid_status"
        ),
        CheckConstraint("attempt BETWEEN 1 AND 5", name="attempt_bounded"),
        Index("ix_workflow_stage_attempts_run_created", "workflow_run_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    stage: Mapped[str] = mapped_column(String(48), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    fencing_token: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowAgentTurn(Base):
    __tablename__ = "workflow_agent_turns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_agent_turns_run_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_workflow_agent_turns_id_org"),
        UniqueConstraint(
            "workflow_run_id",
            "sequence",
            name="uq_workflow_agent_turns_run_sequence",
        ),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint("role IN ('strategist', 'executor')", name="valid_role"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_nonnegative"),
        CheckConstraint("cost_microunits >= 0", name="cost_nonnegative"),
        CheckConstraint("elapsed_seconds >= 0", name="elapsed_nonnegative"),
        Index("ix_workflow_agent_turns_run_phase", "workflow_run_id", "phase_id"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_id: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_model: Mapped[str | None] = mapped_column(String(160))
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(160), nullable=False)
    reference_version: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_sha256: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    observation_sha256: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_microunits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    elapsed_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowAgentToolCall(Base):
    __tablename__ = "workflow_agent_tool_calls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_agent_tool_calls_run_org",
        ),
        ForeignKeyConstraint(
            ["agent_turn_id", "organization_id"],
            ["workflow_agent_turns.id", "workflow_agent_turns.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_agent_tool_calls_turn_org",
        ),
        CheckConstraint("author_attempt BETWEEN 1 AND 5", name="author_attempt_bounded"),
        Index("ix_workflow_agent_tool_calls_run_stage", "workflow_run_id", "stage"),
        Index("ix_workflow_agent_tool_calls_turn", "agent_turn_id"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    agent_turn_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    current_pnn: Mapped[str | None] = mapped_column(String(8))
    author_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    stale: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(160), nullable=False)
    reference_version: Mapped[str] = mapped_column(String(160), nullable=False)
    usage_before: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowCheckpointSet(Base):
    __tablename__ = "workflow_checkpoint_sets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_checkpoint_sets_run_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_workflow_checkpoint_sets_id_org"),
        UniqueConstraint(
            "workflow_run_id", "sequence", name="uq_workflow_checkpoint_sets_run_sequence"
        ),
        CheckConstraint(f"stage IN ({_values(WORKFLOW_STAGES)})", name="valid_stage"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        Index("ix_workflow_checkpoint_sets_run_created", "workflow_run_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    stage_attempt_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(48), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkflowGateReceipt(Base):
    __tablename__ = "workflow_gate_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_gate_receipts_run_org",
        ),
        UniqueConstraint("receipt_sha256", name="uq_workflow_gate_receipts_sha256"),
        CheckConstraint(
            "status IN ('pending', 'passed', 'passed-with-warnings', 'failed', 'stale')",
            name="valid_status",
        ),
        Index("ix_workflow_gate_receipts_run_kind", "workflow_run_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    delegated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delegation_scope: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkflowIntermediateArtifact(Base):
    __tablename__ = "workflow_intermediate_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_workflow_intermediate_artifacts_run_org",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "organization_id"],
            ["artifacts.id", "artifacts.organization_id"],
            ondelete="RESTRICT",
            name="fk_workflow_intermediate_artifacts_artifact_org",
        ),
        UniqueConstraint("artifact_id", name="uq_workflow_intermediate_artifacts_artifact"),
        Index("ix_workflow_intermediate_artifacts_run_kind", "workflow_run_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    checkpoint_set_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    stage: Mapped[str] = mapped_column(String(48), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EffectiveDesignSpecRevision(Base):
    __tablename__ = "effective_design_spec_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_effective_design_spec_revisions_run_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_effective_design_spec_revisions_id_org"),
        UniqueConstraint(
            "workflow_run_id", "revision_number", name="uq_effective_design_spec_revisions_number"
        ),
        UniqueConstraint(
            "presentation_revision_id",
            name="uq_effective_design_spec_revisions_presentation_revision",
        ),
        CheckConstraint("revision_number >= 1", name="revision_number_positive"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    presentation_revision_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    based_on_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    base_design_spec_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_spec_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    spec_lock_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    roster: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DesignSpecEditPatch(Base):
    __tablename__ = "design_spec_edit_patches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_run_id", "organization_id"],
            ["workflow_runs.id", "workflow_runs.organization_id"],
            ondelete="CASCADE",
            name="fk_design_spec_edit_patches_run_org",
        ),
        ForeignKeyConstraint(
            ["effective_spec_revision_id"],
            ["effective_design_spec_revisions.id"],
            ondelete="CASCADE",
            name="fk_design_spec_edit_patches_effective_revision",
        ),
        UniqueConstraint("patch_sha256", name="uq_design_spec_edit_patches_sha256"),
        UniqueConstraint(
            "effective_spec_revision_id",
            "sequence",
            name="uq_design_spec_edit_patches_revision_sequence",
        ),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        Index("ix_design_spec_edit_patches_run_created", "workflow_run_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    base_effective_spec_revision_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), nullable=False
    )
    effective_spec_revision_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    object_key: Mapped[str] = mapped_column(String(160), nullable=False)
    old_value_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    new_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    new_value_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    touches_lock_owned_field: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actor_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    patch_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DataExport(Base):
    __tablename__ = "data_exports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            ondelete="CASCADE",
            name="fk_data_exports_draft_org",
        ),
        UniqueConstraint("id", "organization_id", name="uq_data_exports_id_org"),
        UniqueConstraint("draft_id", "snapshot_sha256", name="uq_data_exports_snapshot"),
        CheckConstraint("status IN ('succeeded', 'failed')", name="valid_status"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    created_by: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProjectCleanupJob(Base):
    __tablename__ = "project_cleanup_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["drafts.id", "drafts.organization_id"],
            ondelete="CASCADE",
            name="fk_project_cleanup_jobs_draft_org",
        ),
        UniqueConstraint("draft_id", name="uq_project_cleanup_jobs_draft"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="valid_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    created_by: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ObjectReconciliationRun(Base):
    __tablename__ = "object_reconciliation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'succeeded_with_alerts', 'failed')",
            name="valid_status",
        ),
        Index("ix_object_reconciliation_runs_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
