"""Transactional orchestration operations for the G02 spike."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    Draft,
    GenerationArtifact,
    GenerationJob,
    GenerationJobSlide,
    GenerationPublication,
    GenerationSnapshot,
    IdempotencyRecord,
    JobEvent,
    Organization,
    OutboxEvent,
    Presentation,
    PublishedFixtureManifest,
    ServiceActor,
    UsageReservation,
    User,
    WorkflowRun,
)
from instant_ppt_domain.runtime_contract import (
    PROCESS_GENERATION_TASK,
    RUNTIME_CONTRACT_VERSION,
)
from instant_ppt_domain.state import (
    InvalidTransition,
    is_terminal_job,
    validate_job_transition,
    validate_slide_transition,
)

SYNTHETIC_ORGANIZATION_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAA"
SYNTHETIC_ACTOR_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAB"


class ResourceNotFound(LookupError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


class LeaseConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CreateJobCommand:
    organization_id: str
    actor_id: str
    draft_id: str
    idempotency_key: str
    request_body: dict[str, Any]
    intent_revision_id: str
    outline_revision_id: str
    template_version_id: str
    slide_count: int
    source_hashes: tuple[str, ...] = ()
    failure_modes: dict[int, str] = field(default_factory=dict)
    step_delay_ms: int = 0
    crash_once_at_position: int | None = None


@dataclass(frozen=True, slots=True)
class CreateJobResult:
    job_id: str
    status_code: int
    headers: dict[str, str]
    body: dict[str, Any]
    replayed: bool


@dataclass(frozen=True, slots=True)
class SlideStart:
    job_id: str
    slide_id: str
    position: int
    failure_mode: str
    attempt: int
    step_delay_ms: int
    crash_now: bool


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def ensure_synthetic_context(
    session: Session, organization_id: str, actor_id: str
) -> tuple[Organization, ServiceActor | User]:
    organization = session.get(Organization, organization_id)
    if organization is None:
        organization = Organization(
            id=organization_id,
            kind="synthetic",
            name="G02 synthetic organization",
            slug=f"synthetic-{organization_id.lower()}",
        )
        session.add(organization)
        session.flush()
    actor = session.get(ServiceActor, actor_id)
    if actor is None:
        user = session.get(User, actor_id)
        if user is not None:
            actor = user
        else:
            actor = ServiceActor(
                id=actor_id,
                organization_id=organization_id,
                name="G02 deterministic service actor",
            )
            session.add(actor)
            session.flush()
    elif actor.organization_id != organization_id:
        raise ResourceNotFound("service actor is not in the requested organization")
    return organization, actor


def _advisory_lock(session: Session, scope: str) -> None:
    lock_key = int.from_bytes(
        hashlib.sha256(scope.encode("utf-8")).digest()[:8], "big", signed=True
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def _job_query(job_id: str, organization_id: str, *, for_update: bool = False) -> Select:
    statement = (
        select(GenerationJob)
        .outerjoin(GenerationSnapshot, GenerationSnapshot.id == GenerationJob.snapshot_id)
        .outerjoin(Draft, Draft.id == GenerationSnapshot.draft_id)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == organization_id,
            Draft.deleted_at.is_(None),
        )
    )
    return statement.with_for_update(of=GenerationJob) if for_update else statement


def get_job(
    session: Session, job_id: str, organization_id: str, *, for_update: bool = False
) -> GenerationJob:
    job = session.scalar(_job_query(job_id, organization_id, for_update=for_update))
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    return job


def serialize_event(event: JobEvent) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "eventId": event.id,
        "jobId": event.job_id,
        "seq": event.seq,
        "type": event.event_type,
        "occurredAt": event.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "snapshotId": event.snapshot_id,
        "slideId": event.slide_id,
        "attempt": event.attempt,
        "stage": event.stage,
        "status": event.status,
        "progress": {
            "completed": event.progress_completed,
            "total": event.progress_total,
        },
        "data": event.data,
        "traceId": event.trace_id,
    }


def serialize_job_snapshot(session: Session, job: GenerationJob) -> dict[str, Any]:
    generation_snapshot = session.get(GenerationSnapshot, job.snapshot_id)
    snapshot_payload = generation_snapshot.payload if generation_snapshot is not None else {}
    slides = session.scalars(
        select(GenerationJobSlide)
        .where(GenerationJobSlide.job_id == job.id)
        .order_by(GenerationJobSlide.position)
    ).all()
    publication = session.scalar(
        select(GenerationPublication)
        .where(GenerationPublication.job_id == job.id)
        .order_by(GenerationPublication.version.desc())
        .limit(1)
    )
    presentation = session.scalar(
        select(Presentation).where(Presentation.generation_job_id == job.id)
    )
    workflow_run = session.scalar(
        select(WorkflowRun).where(
            WorkflowRun.generation_job_id == job.id,
            WorkflowRun.organization_id == job.organization_id,
        )
    )
    generation_artifacts = list(
        session.execute(
            select(GenerationArtifact, Artifact)
            .join(Artifact, Artifact.id == GenerationArtifact.artifact_id)
            .where(
                GenerationArtifact.job_id == job.id,
                GenerationArtifact.publication_version == job.publication_version,
            )
            .order_by(GenerationArtifact.kind, GenerationArtifact.slide_id)
        )
    )
    return {
        "schemaVersion": 1,
        "jobId": job.id,
        "snapshotId": job.snapshot_id,
        "draftId": snapshot_payload.get("draftId"),
        "organizationId": job.organization_id,
        "processor": job.processor,
        "status": job.status,
        "stage": job.stage,
        "mode": snapshot_payload.get("modeId", "native"),
        "engineProfile": snapshot_payload.get("engineProfile"),
        "authoringMode": (snapshot_payload.get("authoringPolicy") or {}).get(
            "mode", "deterministic-template"
        ),
        "authoringDisclosure": (
            "template-limited-editable-draft"
            if (snapshot_payload.get("authoringPolicy") or {}).get(
                "mode", "deterministic-template"
            )
            == "deterministic-template"
            else "agent-authored-editable-draft"
        ),
        "fallbackReason": (snapshot_payload.get("authoringPolicy") or {}).get(
            "fallbackReason", "legacy-snapshot-without-authoring-policy"
        ),
        "templateVersionId": snapshot_payload.get("templateVersionId"),
        "approvalId": snapshot_payload.get("approvalId"),
        "publicationVersion": job.publication_version,
        "publication": (
            {
                "publicationId": publication.id,
                "manifestArtifactId": publication.manifest_artifact_id,
                "manifestSha256": publication.manifest_sha256,
            }
            if publication is not None
            else None
        ),
        "presentation": (
            {
                "presentationId": presentation.id,
                "currentRevisionId": presentation.current_revision_id,
                "status": presentation.status,
            }
            if presentation is not None
            else None
        ),
        "workflow": (
            {
                "workflowRunId": workflow_run.id,
                "status": workflow_run.status,
                "stage": workflow_run.stage,
                "attempt": workflow_run.attempt,
                "checkpointSetId": workflow_run.current_checkpoint_set_id,
                "errorCode": workflow_run.error.get("code"),
                "recoveryAction": (
                    workflow_run.error.get("message")
                    if workflow_run.status == "needs_manual"
                    else None
                ),
            }
            if workflow_run is not None
            else None
        ),
        "artifacts": [
            {
                "artifactId": artifact.id,
                "artifactType": link.kind,
                "slideId": link.slide_id,
                "sha256": artifact.sha256,
                "mediaType": artifact.media_type,
                "sizeBytes": artifact.size_bytes,
            }
            for link, artifact in generation_artifacts
        ],
        "latestSeq": job.latest_seq,
        "terminal": is_terminal_job(job.status),
        "attempt": job.attempt,
        "progress": {"completed": job.progress_completed, "total": job.progress_total},
        "slides": [
            {
                "slideId": slide.slide_id,
                "outlineSlideId": slide.outline_slide_id,
                "position": slide.position,
                "title": slide.title,
                "status": slide.status,
                "stage": slide.stage,
                "attempt": slide.attempt,
                "artifactRef": slide.artifact_ref if job.processor == "fake" else None,
                "renderSha256": slide.render_sha256,
                "errorCode": slide.error_code,
            }
            for slide in slides
        ],
    }


def _append_event(
    session: Session,
    job: GenerationJob,
    event_type: str,
    *,
    slide: GenerationJobSlide | None = None,
    data: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> JobEvent:
    job.latest_seq += 1
    now = utc_now()
    event = JobEvent(
        id=new_ulid(),
        organization_id=job.organization_id,
        job_id=job.id,
        seq=job.latest_seq,
        event_type=event_type,
        snapshot_id=job.snapshot_id,
        slide_id=slide.slide_id if slide else None,
        attempt=slide.attempt if slide else job.attempt,
        stage=slide.stage if slide else job.stage,
        status=slide.status if slide else job.status,
        progress_completed=job.progress_completed,
        progress_total=job.progress_total,
        data=data or {},
        trace_id=trace_id or hashlib.sha256(f"instant-ppt-job:{job.id}".encode()).hexdigest()[:32],
        occurred_at=now,
    )
    session.add(event)
    session.flush()
    session.add(
        OutboxEvent(
            id=new_ulid(),
            organization_id=job.organization_id,
            kind="event",
            aggregate_type="generation_job",
            aggregate_id=job.id,
            dedupe_key=f"event:{event.id}",
            destination=f"job:{job.id}",
            payload=serialize_event(event),
            status="pending",
            available_at=now,
        )
    )
    return event


def _add_task_outbox(session: Session, job: GenerationJob, reason: str) -> None:
    destination = (
        PROCESS_GENERATION_TASK
        if job.processor == "real"
        else "instant_ppt.process_fake_job"
    )
    session.add(
        OutboxEvent(
            id=new_ulid(),
            organization_id=job.organization_id,
            kind="task",
            aggregate_type="generation_job",
            aggregate_id=job.id,
            dedupe_key=f"task:{job.id}:{reason}",
            destination=destination,
            payload={
                "jobId": job.id,
                "organizationId": job.organization_id,
                **(
                    {"runtimeContractVersion": RUNTIME_CONTRACT_VERSION}
                    if job.processor == "real"
                    else {}
                ),
            },
            status="pending",
            available_at=utc_now(),
        )
    )


def create_generation_job(session: Session, command: CreateJobCommand) -> CreateJobResult:
    if not 1 <= command.slide_count <= 30:
        raise ValueError("slide_count must be between 1 and 30")
    if not command.idempotency_key or len(command.idempotency_key) > 200:
        raise ValueError("Idempotency-Key must contain 1 to 200 characters")
    route = f"POST /v1/drafts/{command.draft_id}/generation-jobs"
    request_sha = canonical_sha256(command.request_body)
    _advisory_lock(
        session,
        f"{command.organization_id}:{command.actor_id}:{route}:{command.idempotency_key}",
    )
    ensure_synthetic_context(session, command.organization_id, command.actor_id)
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == command.organization_id,
            IdempotencyRecord.actor_id == command.actor_id,
            IdempotencyRecord.route == route,
            IdempotencyRecord.idempotency_key == command.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_sha256 != request_sha:
            raise IdempotencyConflict("Idempotency-Key was already used with a different body")
        return CreateJobResult(
            job_id=existing.resource_id,
            status_code=existing.response_status,
            headers={str(key): str(value) for key, value in existing.response_headers.items()},
            body=existing.response_body,
            replayed=True,
        )

    created_at = utc_now()
    snapshot_id = new_ulid()
    snapshot_payload = {
        "schemaVersion": 1,
        "snapshotId": snapshot_id,
        "organizationId": command.organization_id,
        "draftId": command.draft_id,
        "intentRevisionId": command.intent_revision_id,
        "outlineRevisionId": command.outline_revision_id,
        "templateVersionId": command.template_version_id,
        "modeId": "native",
        "sourceHashes": sorted(command.source_hashes),
        "promptVersion": "g02-fake-v1",
        "engineVersion": "fake-worker-v1",
        "containerVersion": "g02-local",
        "fontPackVersion": "g01-system-fonts-v1",
        "providerConfigVersion": "fake-provider-v1",
        "createdAt": created_at.isoformat().replace("+00:00", "Z"),
    }
    snapshot_sha = canonical_sha256(snapshot_payload)
    snapshot_payload["snapshotSha256"] = snapshot_sha
    snapshot = GenerationSnapshot(
        id=snapshot_id,
        organization_id=command.organization_id,
        draft_id=command.draft_id,
        intent_revision_id=command.intent_revision_id,
        outline_revision_id=command.outline_revision_id,
        template_version_id=command.template_version_id,
        mode_id="native",
        source_hashes=list(sorted(command.source_hashes)),
        prompt_version="g02-fake-v1",
        engine_version="fake-worker-v1",
        container_version="g02-local",
        font_pack_version="g01-system-fonts-v1",
        provider_config_version="fake-provider-v1",
        snapshot_sha256=snapshot_sha,
        payload=snapshot_payload,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(snapshot)
    # The tenant-scoped composite foreign key is intentionally explicit rather than
    # represented as an ORM relationship. Flush the immutable snapshot first so
    # SQLAlchemy cannot reorder the dependent job insert ahead of it.
    session.flush()
    job = GenerationJob(
        id=new_ulid(),
        organization_id=command.organization_id,
        snapshot_id=snapshot.id,
        processor="fake",
        status="queued",
        stage="deck_planning",
        latest_seq=0,
        attempt=0,
        progress_completed=0,
        progress_total=command.slide_count,
        test_behavior={
            "stepDelayMs": command.step_delay_ms,
            "crashOnceAtPosition": command.crash_once_at_position,
            "crashConsumed": False,
        },
    )
    session.add(job)
    session.flush()
    for position in range(1, command.slide_count + 1):
        slide_id = new_ulid()
        session.add(
            GenerationJobSlide(
                id=new_ulid(),
                organization_id=command.organization_id,
                job_id=job.id,
                slide_id=slide_id,
                position=position,
                status="pending",
                stage="content_generation",
                attempt=0,
                max_attempts=2,
                failure_mode=command.failure_modes.get(position, "none"),
                logical_task_key=(
                    f"{command.organization_id}:{snapshot.id}:slide_generation:{slide_id}"
                ),
            )
        )
    session.add(
        UsageReservation(
            id=new_ulid(),
            organization_id=command.organization_id,
            job_id=job.id,
            status="reserved",
            reserved_units=command.slide_count,
            settled_units=0,
        )
    )
    _append_event(session, job, "job.queued")
    _add_task_outbox(session, job, "initial")
    body = {
        "schemaVersion": 1,
        "resourceId": job.id,
        "resourceType": "generationJob",
        "data": serialize_job_snapshot(session, job),
        "nextCursor": None,
    }
    headers = {"Location": f"/v1/jobs/{job.id}"}
    session.add(
        IdempotencyRecord(
            id=new_ulid(),
            organization_id=command.organization_id,
            actor_id=command.actor_id,
            actor_kind=("user" if session.get(User, command.actor_id) else "service"),
            route=route,
            idempotency_key=command.idempotency_key,
            request_sha256=request_sha,
            response_status=202,
            response_headers=headers,
            response_body=body,
            resource_id=job.id,
            expires_at=created_at + timedelta(days=7),
            created_at=created_at,
            updated_at=created_at,
        )
    )
    return CreateJobResult(
        job_id=job.id, status_code=202, headers=headers, body=body, replayed=False
    )


def claim_job(
    session: Session,
    job_id: str,
    worker_id: str,
    *,
    lease_seconds: int,
) -> GenerationJob | None:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    if is_terminal_job(job.status):
        return None
    now = utc_now()
    if (
        job.lease_owner
        and job.lease_owner != worker_id
        and job.lease_expires_at
        and job.lease_expires_at > now
    ):
        raise LeaseConflict(f"job {job_id} has a live lease")
    job.lease_owner = worker_id
    job.lease_token = new_ulid()
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.heartbeat_at = now
    job.attempt += 1
    job.lock_version += 1
    if job.status == "queued":
        validate_job_transition(job.status, "running")
        job.status = "running"
        job.stage = "slide_generation"
        _append_event(session, job, "job.started")
    return job


def heartbeat_job(session: Session, job_id: str, worker_id: str, *, lease_seconds: int) -> None:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    if job.lease_owner != worker_id:
        raise LeaseConflict(f"worker does not own job lease: {job_id}")
    now = utc_now()
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)


def set_job_stage(session: Session, job_id: str, worker_id: str, stage: str) -> GenerationJob:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    if job.lease_owner != worker_id:
        raise LeaseConflict(f"worker does not own job lease: {job_id}")
    if stage not in {
        "deck_planning",
        "slide_generation",
        "deck_qa",
        "compiling",
        "package_qa",
        "publishing",
    }:
        raise ValueError(f"invalid generation job stage: {stage}")
    if job.stage != stage:
        job.stage = stage
        job.lock_version += 1
        _append_event(session, job, "job.stage.changed", data={"stage": stage})
    return job


def set_slide_stage(
    session: Session,
    job_id: str,
    slide_id: str,
    worker_id: str,
    stage: str,
) -> GenerationJobSlide:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    if job.lease_owner != worker_id:
        raise LeaseConflict(f"worker does not own job lease: {job_id}")
    if stage not in {"content_generation", "rendering", "qa"}:
        raise ValueError(f"invalid generation slide stage: {stage}")
    slide = session.scalar(
        select(GenerationJobSlide)
        .where(GenerationJobSlide.job_id == job_id, GenerationJobSlide.slide_id == slide_id)
        .with_for_update()
    )
    if slide is None:
        raise ResourceNotFound(f"generation slide not found: {slide_id}")
    if slide.status != "running":
        raise InvalidTransition("generation_job_slide", slide.status, "running")
    if slide.stage != stage:
        slide.stage = stage
        slide.lock_version += 1
        _append_event(session, job, "slide.stage.changed", slide=slide, data={"stage": stage})
    return slide


def start_next_slide(session: Session, job_id: str, worker_id: str) -> SlideStart | None:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    if is_terminal_job(job.status) or job.status == "cancel_requested":
        return None
    if job.lease_owner != worker_id:
        raise LeaseConflict(f"worker does not own job lease: {job_id}")
    slide = session.scalar(
        select(GenerationJobSlide)
        .where(
            GenerationJobSlide.job_id == job_id,
            GenerationJobSlide.status.in_(("pending", "retrying", "running")),
        )
        .order_by(GenerationJobSlide.position)
        .with_for_update()
    )
    if slide is None:
        return None
    if slide.status in {"pending", "retrying"}:
        validate_slide_transition(slide.status, "running")
        slide.status = "running"
        slide.stage = "content_generation"
        slide.attempt += 1
        slide.lock_version += 1
        _append_event(session, job, "slide.started", slide=slide)
    behavior = job.test_behavior
    crash_now = bool(
        behavior.get("crashOnceAtPosition") == slide.position
        and not behavior.get("crashConsumed", False)
    )
    if crash_now:
        behavior["crashConsumed"] = True
        job.test_behavior = behavior
    return SlideStart(
        job_id=job.id,
        slide_id=slide.slide_id,
        position=slide.position,
        failure_mode=slide.failure_mode,
        attempt=slide.attempt,
        step_delay_ms=int(behavior.get("stepDelayMs", 0)),
        crash_now=crash_now,
    )


def complete_slide(
    session: Session,
    job_id: str,
    slide_id: str,
    worker_id: str,
    *,
    succeeded: bool,
    artifact_ref: str | None = None,
    render_sha256: str | None = None,
    qa_report: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> GenerationJobSlide:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    if job.lease_owner != worker_id:
        raise LeaseConflict(f"worker does not own job lease: {job_id}")
    slide = session.scalar(
        select(GenerationJobSlide)
        .where(GenerationJobSlide.job_id == job_id, GenerationJobSlide.slide_id == slide_id)
        .with_for_update()
    )
    if slide is None:
        raise ResourceNotFound(f"generation slide not found: {slide_id}")
    if slide.status in {"ready", "failed", "cancelled"}:
        return slide
    target = "ready" if succeeded else "failed"
    validate_slide_transition(slide.status, target)
    slide.status = target
    slide.stage = "qa"
    slide.qa_report = qa_report or {}
    slide.lock_version += 1
    if succeeded:
        slide.artifact_ref = (
            artifact_ref or f"fixture://{job.id}/{slide.slide_id}/attempt-{slide.attempt}"
        )
        slide.render_sha256 = render_sha256
        slide.error_code = None
        job.progress_completed += 1
        _append_event(
            session,
            job,
            "slide.ready",
            slide=slide,
            data={"artifactRef": slide.artifact_ref},
        )
    else:
        slide.error_code = error_code or "slide_render_failed"
        _append_event(
            session,
            job,
            "slide.failed",
            slide=slide,
            data={"errorCode": slide.error_code, "retryable": slide.attempt < slide.max_attempts},
        )
    return slide


def finalize_job(session: Session, job_id: str, worker_id: str) -> str:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise ResourceNotFound(f"generation job not found: {job_id}")
    if is_terminal_job(job.status):
        return job.status
    if job.lease_owner != worker_id:
        raise LeaseConflict(f"worker does not own job lease: {job_id}")
    slides = session.scalars(
        select(GenerationJobSlide)
        .where(GenerationJobSlide.job_id == job.id)
        .order_by(GenerationJobSlide.position)
        .with_for_update()
    ).all()
    if job.status == "cancel_requested":
        for slide in slides:
            if slide.status in {"pending", "running", "retrying"}:
                validate_slide_transition(slide.status, "cancelled")
                slide.status = "cancelled"
        validate_job_transition(job.status, "cancelled")
        job.status = "cancelled"
        job.terminal_at = utc_now()
        reservation = session.scalar(
            select(UsageReservation).where(UsageReservation.job_id == job.id).with_for_update()
        )
        if reservation and reservation.status == "reserved":
            reservation.status = "released"
        _append_event(session, job, "job.cancelled")
        return job.status
    if any(slide.status in {"pending", "running", "retrying"} for slide in slides):
        return job.status
    ready_count = sum(slide.status == "ready" for slide in slides)
    failed_count = sum(slide.status == "failed" for slide in slides)
    if ready_count == len(slides):
        target, event_type = "succeeded", "job.completed"
    elif ready_count > 0 and failed_count > 0:
        target, event_type = "partially_succeeded", "job.partially_completed"
    else:
        target, event_type = "failed", "job.failed"
    validate_job_transition(job.status, target)
    job.stage = "publishing"
    if target in {"succeeded", "partially_succeeded"}:
        manifest_payload = {
            "schemaVersion": 1,
            "jobId": job.id,
            "snapshotId": job.snapshot_id,
            "readySlideIds": [slide.slide_id for slide in slides if slide.status == "ready"],
            "failedSlideIds": [slide.slide_id for slide in slides if slide.status == "failed"],
        }
        session.add(
            PublishedFixtureManifest(
                id=new_ulid(),
                organization_id=job.organization_id,
                job_id=job.id,
                logical_task_key=f"{job.organization_id}:{job.snapshot_id}:publishing",
                manifest_sha256=canonical_sha256(manifest_payload),
                payload=manifest_payload,
            )
        )
        _append_event(session, job, "artifact.published", data=manifest_payload)
    job.status = target
    job.terminal_at = utc_now()
    reservation = session.scalar(
        select(UsageReservation).where(UsageReservation.job_id == job.id).with_for_update()
    )
    if reservation and reservation.status == "reserved":
        reservation.status = "settled"
        reservation.settled_units = ready_count
    _append_event(session, job, event_type)
    return job.status


def request_cancel(session: Session, job_id: str, organization_id: str) -> GenerationJob:
    job = get_job(session, job_id, organization_id, for_update=True)
    if is_terminal_job(job.status) or job.status == "cancel_requested":
        return job
    validate_job_transition(job.status, "cancel_requested")
    job.status = "cancel_requested"
    job.cancel_requested_at = utc_now()
    job.lock_version += 1
    _append_event(session, job, "job.cancel.requested")
    return job


def retry_slide(
    session: Session, job_id: str, slide_id: str, organization_id: str
) -> GenerationJobSlide:
    job = get_job(session, job_id, organization_id, for_update=True)
    slide = session.scalar(
        select(GenerationJobSlide)
        .where(GenerationJobSlide.job_id == job_id, GenerationJobSlide.slide_id == slide_id)
        .with_for_update()
    )
    if slide is None:
        raise ResourceNotFound(f"generation slide not found: {slide_id}")
    if slide.status != "failed":
        return slide
    if slide.attempt >= slide.max_attempts:
        raise InvalidTransition("generation_job_slide", slide.status, "retrying")
    validate_slide_transition(slide.status, "retrying")
    slide.status = "retrying"
    slide.error_code = None
    slide.lock_version += 1
    if is_terminal_job(job.status):
        if job.status not in {"failed", "partially_succeeded"}:
            raise InvalidTransition("generation_job", job.status, "running")
        job.status = "running"
        job.terminal_at = None
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
    _append_event(session, job, "slide.retrying", slide=slide)
    _add_task_outbox(session, job, f"slide-retry:{slide.slide_id}:{slide.attempt + 1}")
    return slide


def list_events_after(
    session: Session, job_id: str, organization_id: str, after_seq: int
) -> list[JobEvent]:
    get_job(session, job_id, organization_id)
    return list(
        session.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.seq > after_seq)
            .order_by(JobEvent.seq)
        ).all()
    )


def count_job_side_effects(session: Session, job_id: str) -> dict[str, int]:
    return {
        "events": session.scalar(
            select(func.count()).select_from(JobEvent).where(JobEvent.job_id == job_id)
        )
        or 0,
        "manifests": session.scalar(
            select(func.count())
            .select_from(PublishedFixtureManifest)
            .where(PublishedFixtureManifest.job_id == job_id)
        )
        or 0,
        "reservations": session.scalar(
            select(func.count())
            .select_from(UsageReservation)
            .where(UsageReservation.job_id == job_id)
        )
        or 0,
    }
