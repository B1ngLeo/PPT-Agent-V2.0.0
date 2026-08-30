"""Durable asynchronous jobs for intent inference and outline generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Membership,
    OutboxEvent,
    OutlineApproval,
    PlanningJob,
    SourceArtifact,
    User,
)
from instant_ppt_domain.runtime_contract import (
    PROCESS_PLANNING_TASK,
    RUNTIME_CONTRACT_VERSION,
)
from instant_ppt_domain.tenancy import TenantContext, append_audit
from instant_ppt_domain.workspace import (
    WorkspaceConflict,
    WorkspaceNotFound,
    WorkspaceValidationError,
    create_intent_revision,
    create_outline_revision,
    get_draft,
    record_provider_call,
    serialize_intent_revision,
    serialize_outline_revision,
)

TERMINAL_PLANNING_STATUSES = frozenset({"succeeded", "failed"})


def _utc(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def serialize_planning_job(job: PlanningJob) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "planningJobId": job.id,
        "draftId": job.draft_id,
        "operation": job.operation,
        "status": job.status,
        "attempt": job.attempt,
        "maxAttempts": job.max_attempts,
        "terminal": job.status in TERMINAL_PLANNING_STATUSES,
        "retryable": job.retryable,
        "errorCode": job.error_code,
        "resultRevisionId": job.result_revision_id,
        "provider": job.provider,
        "model": job.model,
        "createdAt": _utc(job.created_at),
        "updatedAt": _utc(job.updated_at),
        "startedAt": _utc(job.started_at),
        "finishedAt": _utc(job.finished_at),
    }


def get_planning_job(
    session: Session,
    job_id: str,
    organization_id: str,
    *,
    for_update: bool = False,
) -> PlanningJob:
    statement = select(PlanningJob).where(
        PlanningJob.id == job_id,
        PlanningJob.organization_id == organization_id,
    )
    if for_update:
        statement = statement.with_for_update()
    job = session.scalar(statement)
    if job is None:
        raise WorkspaceNotFound("planning job does not exist or is not accessible")
    return job


def latest_planning_job(
    session: Session, draft_id: str, organization_id: str
) -> PlanningJob | None:
    return session.scalar(
        select(PlanningJob)
        .where(
            PlanningJob.draft_id == draft_id,
            PlanningJob.organization_id == organization_id,
        )
        .order_by(PlanningJob.created_at.desc(), PlanningJob.id.desc())
        .limit(1)
    )


def _enqueue(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    operation: str,
    base_revision_id: str | None,
    request_payload: dict[str, Any],
    request_id: str,
) -> PlanningJob:
    active_job_id = session.scalar(
        select(PlanningJob.id).where(
            PlanningJob.draft_id == draft_id,
            PlanningJob.organization_id == context.organization_id,
            PlanningJob.operation == operation,
            PlanningJob.status.in_(("queued", "running", "retrying")),
        )
    )
    if active_job_id is not None:
        raise WorkspaceConflict("a planning job for this operation is already active")
    now = datetime.now(UTC)
    job = PlanningJob(
        id=new_ulid(),
        organization_id=context.organization_id,
        draft_id=draft_id,
        actor_id=context.user_id,
        operation=operation,
        status="queued",
        attempt=0,
        max_attempts=3,
        base_revision_id=base_revision_id,
        request_payload=request_payload,
        retryable=False,
        request_id=request_id,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    session.add(
        OutboxEvent(
            id=new_ulid(),
            organization_id=context.organization_id,
            kind="task",
            aggregate_type="planning_job",
            aggregate_id=job.id,
            dedupe_key=f"planning:{job.id}:initial",
            destination=PROCESS_PLANNING_TASK,
            payload={
                "jobId": job.id,
                "organizationId": context.organization_id,
                "runtimeContractVersion": RUNTIME_CONTRACT_VERSION,
                "reason": "initial",
            },
            status="pending",
            available_at=now,
        )
    )
    append_audit(
        session,
        context,
        resource_type="planning_job",
        resource_id=job.id,
        action=f"planning.{operation}.queued",
        request_id=request_id,
        outcome="succeeded",
        details={"draftId": draft_id},
    )
    session.flush()
    return job


def enqueue_intent_job(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    language: str,
    base_revision_id: str | None,
    request_id: str,
) -> PlanningJob:
    draft = get_draft(session, draft_id, context.organization_id, for_update=True)
    if draft.current_intent_revision_id != base_revision_id:
        raise WorkspaceConflict("intent base revision is stale")
    source_refs = (
        list(
            session.scalars(
                select(SourceArtifact.artifact_id)
                .where(
                    SourceArtifact.source_id == draft.source_id,
                    SourceArtifact.organization_id == context.organization_id,
                )
                .order_by(SourceArtifact.kind, SourceArtifact.id)
            )
        )
        if draft.source_id
        else []
    )
    return _enqueue(
        session,
        context,
        draft.id,
        operation="intent_infer",
        base_revision_id=base_revision_id,
        request_payload={
            "topic": draft.topic,
            "sourceRefs": source_refs,
            "language": language,
        },
        request_id=request_id,
    )


def enqueue_outline_job(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    action: str,
    instruction: str,
    target_slide_id: str | None,
    base_revision_id: str | None,
    request_id: str,
) -> PlanningJob:
    draft = get_draft(session, draft_id, context.organization_id, for_update=True)
    if not draft.current_intent_revision_id:
        raise WorkspaceValidationError("an intent revision is required")
    if draft.current_outline_revision_id != base_revision_id:
        raise WorkspaceConflict("outline base revision is stale")
    return _enqueue(
        session,
        context,
        draft.id,
        operation="outline_generate",
        base_revision_id=base_revision_id,
        request_payload={
            "intentRevisionId": draft.current_intent_revision_id,
            "existingOutlineRevisionId": draft.current_outline_revision_id,
            "action": action,
            "instruction": instruction,
            "targetSlideId": target_slide_id,
        },
        request_id=request_id,
    )


def enqueue_visual_style_job(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    approval_id: str | None,
    request_id: str,
) -> PlanningJob:
    draft = get_draft(session, draft_id, context.organization_id, for_update=True)
    if not draft.approved_outline_revision_id:
        raise WorkspaceValidationError("an approved outline is required")
    approval = session.scalar(
        select(OutlineApproval).where(
            OutlineApproval.id == approval_id,
            OutlineApproval.draft_id == draft.id,
            OutlineApproval.organization_id == context.organization_id,
            OutlineApproval.outline_revision_id == draft.approved_outline_revision_id,
        )
    )
    if approval is None:
        raise WorkspaceConflict("visual-style approval boundary is stale")
    return _enqueue(
        session,
        context,
        draft.id,
        operation="visual_style_generate",
        base_revision_id=approval.id,
        request_payload={
            "approvalId": approval.id,
            "intentRevisionId": approval.intent_revision_id,
            "outlineRevisionId": approval.outline_revision_id,
            "templateVersionId": approval.template_version_id,
        },
        request_id=request_id,
    )


def resolve_job_context(session: Session, job: PlanningJob) -> TenantContext:
    user = session.scalar(select(User).where(User.id == job.actor_id))
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == job.actor_id,
            Membership.organization_id == job.organization_id,
            Membership.status == "active",
        )
    )
    if user is None or membership is None:
        raise WorkspaceNotFound("planning job actor is no longer accessible")
    return TenantContext(
        user_id=user.id,
        organization_id=membership.organization_id,
        membership_id=membership.id,
        role=membership.role,
        issuer=user.issuer,
        subject=user.subject,
    )


def start_planning_attempt(session: Session, job_id: str, organization_id: str) -> PlanningJob:
    job = get_planning_job(session, job_id, organization_id, for_update=True)
    if job.status in TERMINAL_PLANNING_STATUSES:
        return job
    if job.attempt >= job.max_attempts:
        job.status = "failed"
        job.retryable = False
        job.error_code = job.error_code or "PLANNING_RETRY_LIMIT_REACHED"
        job.finished_at = datetime.now(UTC)
        return job
    now = datetime.now(UTC)
    job.attempt += 1
    job.status = "running"
    job.retryable = False
    job.error_code = None
    job.started_at = job.started_at or now
    job.updated_at = now
    session.flush()
    return job


def finish_planning_failure(
    session: Session,
    job_id: str,
    organization_id: str,
    *,
    error_code: str,
    retryable: bool,
) -> PlanningJob:
    job = get_planning_job(session, job_id, organization_id, for_update=True)
    if job.status in TERMINAL_PLANNING_STATUSES:
        return job
    can_retry = retryable and job.attempt < job.max_attempts
    now = datetime.now(UTC)
    job.status = "retrying" if can_retry else "failed"
    job.retryable = retryable
    job.error_code = error_code[:80]
    job.updated_at = now
    if not can_retry:
        job.finished_at = now
    session.flush()
    return job


def finish_planning_success(
    session: Session,
    job_id: str,
    organization_id: str,
    *,
    result: dict[str, Any],
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    repair_count: int,
) -> PlanningJob:
    job = get_planning_job(session, job_id, organization_id, for_update=True)
    if job.status == "succeeded":
        return job
    if job.status == "failed":
        raise WorkspaceConflict("failed planning job cannot publish a result")
    context = resolve_job_context(session, job)
    now = datetime.now(UTC)
    purpose = (
        "intent_infer"
        if job.operation == "intent_infer"
        else (
            "visual_style_generate"
            if job.operation == "visual_style_generate"
            else (
                "outline_generate"
                if job.request_payload.get("action") == "generate"
                else f"outline_{job.request_payload.get('action')}"
            )
        )
    )
    provider_call = record_provider_call(
        session,
        context,
        job.draft_id,
        provider=provider,
        model=model,
        purpose=purpose,
        request_value={"draftId": job.draft_id, **dict(job.request_payload)},
        status="succeeded",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        repair_count=repair_count,
        started_at=job.started_at or now,
        finished_at=now,
    )
    if job.operation == "intent_infer":
        revision = create_intent_revision(
            session,
            context,
            job.draft_id,
            data=result,
            based_on_revision_id=job.base_revision_id,
            actor_kind="ai",
            provider_call_id=provider_call.id,
            request_id=job.request_id,
        )
    elif job.operation == "outline_generate":
        slides = [
            {
                **slide,
                "outlineSlideId": slide.get("outlineSlideId") or new_ulid(),
            }
            for slide in result["slides"]
        ]
        revision = create_outline_revision(
            session,
            context,
            job.draft_id,
            story_summary=result["storySummary"],
            target_slide_count=result["targetSlideCount"],
            slides=slides,
            based_on_revision_id=job.base_revision_id,
            actor_kind="ai",
            operation=str(job.request_payload.get("action") or "generate"),
            provider_call_id=provider_call.id,
            request_id=job.request_id,
        )
    elif job.operation == "visual_style_generate":
        job.result_payload = dict(result)
        revision = None
    else:
        raise WorkspaceValidationError("planning job operation is invalid")
    job.status = "succeeded"
    job.result_revision_id = revision.id if revision is not None else None
    job.provider = provider
    job.model = model
    job.error_code = None
    job.retryable = False
    job.finished_at = now
    job.updated_at = now
    session.flush()
    return job


def planning_job_result(session: Session, job: PlanningJob) -> dict[str, Any] | None:
    if job.status != "succeeded":
        return None
    if job.operation == "visual_style_generate":
        return dict(job.result_payload) if job.result_payload else None
    if not job.result_revision_id:
        return None
    if job.operation == "intent_infer":
        from instant_ppt_domain.workspace import get_intent_revision

        return serialize_intent_revision(
            get_intent_revision(session, job.result_revision_id, job.organization_id)
        )
    from instant_ppt_domain.workspace import get_outline_revision

    return serialize_outline_revision(
        session,
        get_outline_revision(session, job.result_revision_id, job.organization_id),
    )
