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
TERMINAL_JOB_STATUSES = frozenset(
    {"cancelled", "succeeded", "partially_succeeded", "failed"}
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(ULID_LENGTH), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="synthetic")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
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
        ForeignKeyConstraint(
            ["actor_id", "organization_id"],
            ["service_actors.id", "service_actors.organization_id"],
            ondelete="CASCADE",
            name="fk_idempotency_records_actor_org",
        ),
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
