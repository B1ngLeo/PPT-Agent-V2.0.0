"""G07 immutable presentation editing, export, history, and project lifecycle services."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from instant_ppt_domain.artifacts import tenant_object_key
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    DataExport,
    Draft,
    ExportJob,
    GenerationJob,
    GenerationSnapshot,
    IntentRevision,
    OutboxEvent,
    OutlineRevision,
    OutlineSlide,
    Presentation,
    PresentationRevision,
    ProjectCleanupJob,
    SlideRegenerationJob,
    SlideVersion,
)
from instant_ppt_domain.service import canonical_sha256
from instant_ppt_domain.tenancy import TenantContext, append_audit


class PresentationNotFound(LookupError):
    pass


class PresentationConflict(RuntimeError):
    pass


class PresentationValidationError(ValueError):
    pass


class WritableObjectStore(Protocol):
    def put_bytes(self, object_key: str, payload: bytes, media_type: str) -> None: ...


def _utc(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def get_presentation(
    session: Session, presentation_id: str, organization_id: str, *, for_update: bool = False
) -> Presentation:
    statement = (
        select(Presentation)
        .join(Draft, Draft.id == Presentation.draft_id)
        .where(
            Presentation.id == presentation_id,
            Presentation.organization_id == organization_id,
            Presentation.deleted_at.is_(None),
            Draft.deleted_at.is_(None),
        )
    )
    row = session.scalar(statement.with_for_update() if for_update else statement)
    if row is None:
        raise PresentationNotFound("presentation does not exist or is not accessible")
    return row


def get_revision(
    session: Session,
    revision_id: str,
    organization_id: str,
    *,
    presentation_id: str | None = None,
) -> PresentationRevision:
    statement = select(PresentationRevision).where(
        PresentationRevision.id == revision_id,
        PresentationRevision.organization_id == organization_id,
    )
    if presentation_id:
        statement = statement.where(PresentationRevision.presentation_id == presentation_id)
    row = session.scalar(statement)
    if row is None:
        raise PresentationNotFound("presentation revision does not exist or is not accessible")
    get_presentation(session, row.presentation_id, organization_id)
    return row


def _revision_slides(session: Session, revision_id: str) -> list[SlideVersion]:
    return list(
        session.scalars(
            select(SlideVersion)
            .where(SlideVersion.presentation_revision_id == revision_id)
            .order_by(SlideVersion.position)
        )
    )


def serialize_revision(session: Session, row: PresentationRevision) -> dict[str, Any]:
    return {
        **row.payload,
        "presentationRevisionId": row.id,
        "presentationId": row.presentation_id,
        "basedOnRevisionId": row.based_on_revision_id,
        "actorId": row.actor_id,
        "revisionNumber": row.revision_number,
        "operation": row.operation,
        "partial": row.partial,
        "acceptedMissing": row.accepted_missing,
        "manifestArtifactId": row.manifest_artifact_id,
        "payloadSha256": row.payload_sha256,
        "createdAt": _utc(row.created_at),
        "slides": [serialize_slide(slide) for slide in _revision_slides(session, row.id)],
    }


def serialize_slide(row: SlideVersion) -> dict[str, Any]:
    return {
        "slideVersionId": row.id,
        "slideId": row.slide_id,
        "outlineSlideId": row.outline_slide_id,
        "position": row.position,
        "status": row.status,
        "title": row.title,
        "body": row.body,
        "artifactId": row.artifact_id,
        "sourceSlideVersionId": row.source_slide_version_id,
        "errorCode": row.error_code,
        "payloadSha256": row.payload_sha256,
    }


def serialize_presentation(session: Session, row: Presentation) -> dict[str, Any]:
    revision = (
        get_revision(session, row.current_revision_id, row.organization_id)
        if row.current_revision_id
        else None
    )
    return {
        "presentationId": row.id,
        "draftId": row.draft_id,
        "generationJobId": row.generation_job_id,
        "title": row.title,
        "status": row.status,
        "currentRevisionId": row.current_revision_id,
        "lockVersion": row.lock_version,
        "createdAt": _utc(row.created_at),
        "updatedAt": _utc(row.updated_at),
        "currentRevision": serialize_revision(session, revision) if revision else None,
    }


def list_revisions(
    session: Session,
    presentation_id: str,
    organization_id: str,
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[PresentationRevision], str | None]:
    get_presentation(session, presentation_id, organization_id)
    statement = select(PresentationRevision).where(
        PresentationRevision.presentation_id == presentation_id,
        PresentationRevision.organization_id == organization_id,
    )
    if cursor:
        statement = statement.where(PresentationRevision.id < cursor)
    rows = list(
        session.scalars(statement.order_by(PresentationRevision.id.desc()).limit(limit + 1))
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    return visible, visible[-1].id if has_more else None


def _publish_json_artifact(
    session: Session,
    *,
    organization_id: str,
    artifact_id: str,
    artifact_type: str,
    payload: dict[str, Any],
    object_store: WritableObjectStore,
    retention_days: int = 30,
) -> Artifact:
    content = canonical_bytes(payload)
    object_key = tenant_object_key(organization_id, "published", artifact_id)
    object_store.put_bytes(object_key, content, "application/json")
    row = Artifact(
        id=artifact_id,
        organization_id=organization_id,
        artifact_type=artifact_type,
        partition="published",
        object_key=object_key,
        sha256=hashlib.sha256(content).hexdigest(),
        media_type="application/json",
        size_bytes=len(content),
        status="published",
        retention_expires_at=datetime.now(UTC) + timedelta(days=retention_days),
    )
    session.add(row)
    session.flush()
    return row


def _editable_slide(row: SlideVersion) -> dict[str, Any]:
    return {
        "slideId": row.slide_id,
        "outlineSlideId": row.outline_slide_id,
        "position": row.position,
        "status": row.status,
        "title": row.title,
        "body": list(row.body),
        "artifactId": row.artifact_id,
        "errorCode": row.error_code,
        "sourceSlideVersionId": row.id,
    }


def create_revision(
    session: Session,
    context: TenantContext,
    presentation_id: str,
    *,
    base_revision_id: str,
    operations: list[dict[str, Any]],
    object_store: WritableObjectStore,
    request_id: str,
) -> PresentationRevision:
    presentation = get_presentation(
        session, presentation_id, context.organization_id, for_update=True
    )
    if presentation.current_revision_id != base_revision_id:
        raise PresentationConflict("baseRevisionId is not the current presentation revision")
    base = get_revision(
        session, base_revision_id, context.organization_id, presentation_id=presentation.id
    )
    slides = [_editable_slide(row) for row in _revision_slides(session, base.id)]
    accepted_missing = base.accepted_missing
    if not operations:
        raise PresentationValidationError("at least one revision operation is required")
    operation_names: list[str] = []
    for operation in operations:
        kind = str(operation.get("type") or "").strip()
        operation_names.append(kind)
        slide_id = str(operation.get("slideId") or "")
        index = next((i for i, item in enumerate(slides) if item["slideId"] == slide_id), -1)
        if kind == "update_text":
            if index < 0:
                raise PresentationValidationError("update_text slideId does not exist")
            if "title" not in operation and "body" not in operation:
                raise PresentationValidationError("update_text requires title or body")
            if "title" in operation:
                title = str(operation["title"]).strip()
                if not title or len(title) > 300:
                    raise PresentationValidationError(
                        "slide title must contain 1 to 300 characters"
                    )
                slides[index]["title"] = title
            if "body" in operation:
                body = operation["body"]
                if not isinstance(body, list) or not all(isinstance(item, str) for item in body):
                    raise PresentationValidationError("slide body must be a string array")
                slides[index]["body"] = [item[:2000] for item in body]
        elif kind == "move":
            if index < 0:
                raise PresentationValidationError("move slideId does not exist")
            position = operation.get("position")
            if not isinstance(position, int) or not 1 <= position <= len(slides):
                raise PresentationValidationError("move position is outside the slide range")
            item = slides.pop(index)
            slides.insert(position - 1, item)
        elif kind == "delete":
            if index < 0:
                raise PresentationValidationError("delete slideId does not exist")
            slides.pop(index)
        elif kind == "accept_missing":
            accepted_missing = True
        else:
            raise PresentationValidationError(f"unsupported presentation operation: {kind}")
    if not slides:
        raise PresentationValidationError("a presentation must retain at least one slide")
    for index, slide in enumerate(slides, start=1):
        slide["position"] = index
    partial = any(slide["status"] == "failed" for slide in slides)
    revision_number = (
        int(
            session.scalar(
                select(func.max(PresentationRevision.revision_number)).where(
                    PresentationRevision.presentation_id == presentation.id
                )
            )
            or 0
        )
        + 1
    )
    revision_id = new_ulid()
    payload = {
        "schemaVersion": 1,
        "presentationRevisionId": revision_id,
        "presentationId": presentation.id,
        "generationJobId": presentation.generation_job_id,
        "snapshotId": base.snapshot_id,
        "revisionNumber": revision_number,
        "basedOnRevisionId": base.id,
        "operationSet": operations,
        "partial": partial,
        "acceptedMissing": accepted_missing,
        "slides": [
            {key: value for key, value in slide.items() if key != "sourceSlideVersionId"}
            for slide in slides
        ],
    }
    manifest_id = new_ulid()
    manifest_payload = {
        "schemaVersion": 1,
        "artifactId": manifest_id,
        "artifactType": "presentation_revision_manifest",
        "organizationId": context.organization_id,
        "presentationId": presentation.id,
        "presentationRevisionId": revision_id,
        "basedOnRevisionId": base.id,
        "payloadSha256": canonical_sha256(payload),
        "slides": payload["slides"],
    }
    _publish_json_artifact(
        session,
        organization_id=context.organization_id,
        artifact_id=manifest_id,
        artifact_type="presentation_revision_manifest",
        payload=manifest_payload,
        object_store=object_store,
    )
    revision = PresentationRevision(
        id=revision_id,
        organization_id=context.organization_id,
        presentation_id=presentation.id,
        generation_job_id=presentation.generation_job_id,
        snapshot_id=base.snapshot_id,
        manifest_artifact_id=manifest_id,
        based_on_revision_id=base.id,
        actor_id=context.user_id,
        revision_number=revision_number,
        operation="operation_set",
        partial=partial,
        accepted_missing=accepted_missing,
        payload=payload,
        payload_sha256=canonical_sha256(payload),
    )
    session.add(revision)
    session.flush()
    for slide in slides:
        slide_payload = {
            key: value for key, value in slide.items() if key != "sourceSlideVersionId"
        }
        session.add(
            SlideVersion(
                id=new_ulid(),
                organization_id=context.organization_id,
                presentation_revision_id=revision.id,
                slide_id=slide["slideId"],
                outline_slide_id=slide["outlineSlideId"],
                position=slide["position"],
                status=slide["status"],
                title=slide["title"],
                body=slide["body"],
                artifact_id=slide["artifactId"],
                source_slide_version_id=slide["sourceSlideVersionId"],
                error_code=slide["errorCode"],
                payload_sha256=canonical_sha256(slide_payload),
            )
        )
    presentation.current_revision_id = revision.id
    presentation.status = "partial" if partial else "ready"
    presentation.lock_version += 1
    append_audit(
        session,
        context,
        resource_type="presentation_revision",
        resource_id=revision.id,
        action="presentation.revision.created",
        request_id=request_id,
        outcome="succeeded",
        details={"presentationId": presentation.id, "operationCount": len(operations)},
    )
    session.flush()
    return revision


def _task_outbox(
    session: Session,
    *,
    organization_id: str,
    aggregate_type: str,
    aggregate_id: str,
    destination: str,
) -> None:
    session.add(
        OutboxEvent(
            id=new_ulid(),
            organization_id=organization_id,
            kind="task",
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            dedupe_key=f"task:{aggregate_type}:{aggregate_id}:1",
            destination=destination,
            payload={"jobId": aggregate_id, "organizationId": organization_id},
            status="pending",
            available_at=datetime.now(UTC),
        )
    )


def create_regeneration_job(
    session: Session,
    context: TenantContext,
    presentation_id: str,
    slide_id: str,
    *,
    base_revision_id: str,
    instruction: str,
    request_id: str,
) -> SlideRegenerationJob:
    presentation = get_presentation(
        session, presentation_id, context.organization_id, for_update=True
    )
    if presentation.current_revision_id != base_revision_id:
        raise PresentationConflict("baseRevisionId is not the current presentation revision")
    base = get_revision(
        session, base_revision_id, context.organization_id, presentation_id=presentation.id
    )
    if not any(slide.slide_id == slide_id for slide in _revision_slides(session, base.id)):
        raise PresentationValidationError("slideId does not exist in the base revision")
    if len(instruction) > 2000:
        raise PresentationValidationError("regeneration instruction exceeds 2000 characters")
    row = SlideRegenerationJob(
        id=new_ulid(),
        organization_id=context.organization_id,
        presentation_id=presentation.id,
        base_revision_id=base.id,
        slide_id=slide_id,
        created_by=context.user_id,
        instruction=instruction.strip(),
        status="queued",
    )
    session.add(row)
    _task_outbox(
        session,
        organization_id=context.organization_id,
        aggregate_type="slide_regeneration_job",
        aggregate_id=row.id,
        destination="instant_ppt.process_slide_regeneration",
    )
    append_audit(
        session,
        context,
        resource_type="slide_regeneration_job",
        resource_id=row.id,
        action="presentation.slide_regeneration.queued",
        request_id=request_id,
        outcome="succeeded",
        details={"presentationId": presentation.id, "slideId": slide_id},
    )
    session.flush()
    return row


def serialize_regeneration_job(row: SlideRegenerationJob) -> dict[str, Any]:
    return {
        "regenerationJobId": row.id,
        "presentationId": row.presentation_id,
        "baseRevisionId": row.base_revision_id,
        "slideId": row.slide_id,
        "status": row.status,
        "attempt": row.attempt,
        "resultRevisionId": row.result_revision_id,
        "resultArtifactId": row.result_artifact_id,
        "errorCode": row.error_code,
        "createdAt": _utc(row.created_at),
        "updatedAt": _utc(row.updated_at),
        "terminalAt": _utc(row.terminal_at),
    }


def create_export_job(
    session: Session,
    context: TenantContext,
    presentation_id: str,
    *,
    revision_id: str,
    options: dict[str, Any],
    request_id: str,
) -> ExportJob:
    presentation = get_presentation(session, presentation_id, context.organization_id)
    revision = get_revision(
        session, revision_id, context.organization_id, presentation_id=presentation.id
    )
    if revision.partial and not revision.accepted_missing:
        raise PresentationValidationError(
            "partial revisions require explicit accept_missing before export"
        )
    options_sha = canonical_sha256(options)
    existing = session.scalar(
        select(ExportJob).where(
            ExportJob.presentation_revision_id == revision.id,
            ExportJob.options_sha256 == options_sha,
        )
    )
    if existing is not None:
        return existing
    row = ExportJob(
        id=new_ulid(),
        organization_id=context.organization_id,
        presentation_id=presentation.id,
        presentation_revision_id=revision.id,
        created_by=context.user_id,
        status="queued",
        stage="queued",
        options=options,
        options_sha256=options_sha,
    )
    session.add(row)
    _task_outbox(
        session,
        organization_id=context.organization_id,
        aggregate_type="export_job",
        aggregate_id=row.id,
        destination="instant_ppt.process_export",
    )
    append_audit(
        session,
        context,
        resource_type="export_job",
        resource_id=row.id,
        action="presentation.export.queued",
        request_id=request_id,
        outcome="succeeded",
        details={"presentationId": presentation.id, "revisionId": revision.id},
    )
    session.flush()
    return row


def get_export_job(session: Session, export_id: str, organization_id: str) -> ExportJob:
    row = session.scalar(
        select(ExportJob).where(
            ExportJob.id == export_id, ExportJob.organization_id == organization_id
        )
    )
    if row is None:
        raise PresentationNotFound("export does not exist or is not accessible")
    get_presentation(session, row.presentation_id, organization_id)
    return row


def serialize_export_job(row: ExportJob) -> dict[str, Any]:
    return {
        "exportId": row.id,
        "presentationId": row.presentation_id,
        "presentationRevisionId": row.presentation_revision_id,
        "status": row.status,
        "stage": row.stage,
        "options": row.options,
        "artifactId": row.artifact_id,
        "manifestArtifactId": row.manifest_artifact_id,
        "errorCode": row.error_code,
        "createdAt": _utc(row.created_at),
        "updatedAt": _utc(row.updated_at),
        "terminalAt": _utc(row.terminal_at),
    }


def export_draft_data(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    object_store: WritableObjectStore,
    request_id: str,
) -> DataExport:
    draft = session.scalar(
        select(Draft).where(
            Draft.id == draft_id,
            Draft.organization_id == context.organization_id,
            Draft.deleted_at.is_(None),
        )
    )
    if draft is None:
        raise PresentationNotFound("draft does not exist or is not accessible")
    intents = list(
        session.scalars(
            select(IntentRevision)
            .where(IntentRevision.draft_id == draft.id)
            .order_by(IntentRevision.created_at)
        )
    )
    outlines = list(
        session.scalars(
            select(OutlineRevision)
            .where(OutlineRevision.draft_id == draft.id)
            .order_by(OutlineRevision.created_at)
        )
    )
    presentations = list(
        session.scalars(
            select(Presentation).where(
                Presentation.draft_id == draft.id, Presentation.deleted_at.is_(None)
            )
        )
    )
    payload = {
        "schemaVersion": 1,
        "exportedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "organizationId": context.organization_id,
        "draft": {
            "draftId": draft.id,
            "title": draft.title,
            "topic": draft.topic,
            "status": draft.status,
            "sourceId": draft.source_id,
            "templateVersionId": draft.template_version_id,
            "lockVersion": draft.lock_version,
        },
        "intentRevisions": [row.payload for row in intents],
        "outlineRevisions": [
            {
                "schemaVersion": 1,
                "outlineRevisionId": row.id,
                "basedOnRevisionId": row.based_on_revision_id,
                "operation": row.operation,
                "storySummary": row.story_summary,
                "targetSlideCount": row.target_slide_count,
                "payloadSha256": row.payload_sha256,
                "slides": [
                    {
                        "outlineSlideId": slide.outline_slide_id,
                        "position": slide.position,
                        "type": slide.slide_type,
                        "title": slide.title,
                        "keyPoints": slide.key_points,
                    }
                    for slide in session.scalars(
                        select(OutlineSlide)
                        .where(OutlineSlide.outline_revision_id == row.id)
                        .order_by(OutlineSlide.position)
                    )
                ],
            }
            for row in outlines
        ],
        "presentations": [serialize_presentation(session, row) for row in presentations],
    }
    snapshot_sha = canonical_sha256(payload)
    existing = session.scalar(
        select(DataExport).where(
            DataExport.draft_id == draft.id, DataExport.snapshot_sha256 == snapshot_sha
        )
    )
    if existing is not None:
        return existing
    row_id = new_ulid()
    artifact_id = new_ulid()
    _publish_json_artifact(
        session,
        organization_id=context.organization_id,
        artifact_id=artifact_id,
        artifact_type="project_data_export",
        payload=payload,
        object_store=object_store,
        retention_days=7,
    )
    row = DataExport(
        id=row_id,
        organization_id=context.organization_id,
        draft_id=draft.id,
        created_by=context.user_id,
        status="succeeded",
        snapshot_sha256=snapshot_sha,
        artifact_id=artifact_id,
        payload=payload,
    )
    session.add(row)
    append_audit(
        session,
        context,
        resource_type="data_export",
        resource_id=row.id,
        action="draft.data_export.created",
        request_id=request_id,
        outcome="succeeded",
        details={"draftId": draft.id, "snapshotSha256": snapshot_sha},
    )
    session.flush()
    return row


def get_data_export(session: Session, export_id: str, organization_id: str) -> DataExport:
    row = session.scalar(
        select(DataExport).where(
            DataExport.id == export_id, DataExport.organization_id == organization_id
        )
    )
    if row is None:
        raise PresentationNotFound("data export does not exist or is not accessible")
    draft = session.scalar(
        select(Draft).where(
            Draft.id == row.draft_id,
            Draft.organization_id == organization_id,
            Draft.deleted_at.is_(None),
        )
    )
    if draft is None:
        raise PresentationNotFound("data export does not exist or is not accessible")
    return row


def serialize_data_export(row: DataExport) -> dict[str, Any]:
    return {
        "dataExportId": row.id,
        "draftId": row.draft_id,
        "status": row.status,
        "snapshotSha256": row.snapshot_sha256,
        "artifactId": row.artifact_id,
        "createdAt": _utc(row.created_at),
    }


def queue_project_cleanup(
    session: Session, context: TenantContext, draft: Draft, *, request_id: str
) -> ProjectCleanupJob:
    existing = session.scalar(
        select(ProjectCleanupJob).where(ProjectCleanupJob.draft_id == draft.id)
    )
    if existing is not None:
        return existing
    row = ProjectCleanupJob(
        id=new_ulid(),
        organization_id=context.organization_id,
        draft_id=draft.id,
        created_by=context.user_id,
        status="queued",
        result={},
    )
    session.add(row)
    _task_outbox(
        session,
        organization_id=context.organization_id,
        aggregate_type="project_cleanup_job",
        aggregate_id=row.id,
        destination="instant_ppt.process_project_cleanup",
    )
    append_audit(
        session,
        context,
        resource_type="project_cleanup_job",
        resource_id=row.id,
        action="draft.cleanup.queued",
        request_id=request_id,
        outcome="succeeded",
        details={"draftId": draft.id},
    )
    session.flush()
    return row


def generation_job_is_visible(session: Session, job: GenerationJob) -> bool:
    snapshot = session.scalar(
        select(GenerationSnapshot).where(GenerationSnapshot.id == job.snapshot_id)
    )
    if snapshot is None:
        return True
    draft = session.scalar(select(Draft).where(Draft.id == snapshot.draft_id))
    return draft is None or draft.deleted_at is None
