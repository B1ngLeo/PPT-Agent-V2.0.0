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
TERMINAL_JOB_STATUSES = frozenset(
    {"cancelled", "succeeded", "partially_succeeded", "failed"}
)


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
        UniqueConstraint(
            "personal_owner_user_id", name="uq_organizations_personal_owner_user"
        ),
        CheckConstraint(
            f"kind IN ({_values(ORGANIZATION_KINDS)})", name="valid_kind"
        ),
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
        UniqueConstraint(
            "organization_id", "user_id", name="uq_memberships_organization_user"
        ),
        CheckConstraint(f"role IN ({_values(MEMBERSHIP_ROLES)})", name="valid_role"),
        CheckConstraint(
            f"status IN ({_values(MEMBERSHIP_STATUSES)})", name="valid_status"
        ),
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
        UniqueConstraint(
            "id", "organization_id", name="uq_generation_snapshots_id_organization"
        ),
        UniqueConstraint(
            "organization_id", "snapshot_sha256", name="uq_generation_snapshots_org_sha"
        ),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    draft_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
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
        CheckConstraint("latest_seq >= 0", name="latest_seq_nonnegative"),
        CheckConstraint("attempt >= 0", name="attempt_nonnegative"),
        Index("ix_generation_jobs_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="deck_planning")
    latest_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="content_generation"
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    failure_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    logical_task_key: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(320))
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
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    job_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    reserved_units: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
        CheckConstraint("max_concurrent_jobs >= 1", name="concurrency_positive"),
    )

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False, default="p1-default")
    max_slides_per_deck: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    monthly_slide_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
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
        UniqueConstraint(
            "organization_id", "dedupe_key", name="uq_usage_ledger_org_dedupe"
        ),
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
        CheckConstraint(
            f"partition IN ({_values(ARTIFACT_PARTITIONS)})", name="valid_partition"
        ),
        CheckConstraint(
            f"status IN ({_values(ARTIFACT_STATUSES)})", name="valid_status"
        ),
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
        CheckConstraint(
            f"scan_status IN ({_values(SCAN_STATUSES)})", name="valid_scan_status"
        ),
        CheckConstraint(
            f"parse_status IN ({_values(PARSE_STATUSES)})", name="valid_parse_status"
        ),
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
        CheckConstraint(
            f"status IN ({_values(UPLOAD_SESSION_STATUSES)})", name="valid_status"
        ),
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
        CheckConstraint(
            f"kind IN ({_values(SOURCE_ARTIFACT_KINDS)})", name="valid_kind"
        ),
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
