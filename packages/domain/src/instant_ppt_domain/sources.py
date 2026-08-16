"""Tenant-safe source upload sessions and quarantine completion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from instant_ppt_domain.artifacts import tenant_object_key
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    OutboxEvent,
    Source,
    SourceArtifact,
    UploadSession,
)
from instant_ppt_domain.tenancy import TenantContext, append_audit

MAX_SOURCE_BYTES = 25 * 1024 * 1024
SOURCE_RETENTION_DAYS = 30
SUPPORTED_SOURCE_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
}
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class SourceNotFound(LookupError):
    pass


class UploadValidationError(ValueError):
    pass


class UploadObjectUnavailable(RuntimeError):
    pass


class SourceRetryRejected(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UploadPolicy:
    url: str
    fields: dict[str, str]


@dataclass(frozen=True, slots=True)
class ObjectDigest:
    size_bytes: int
    sha256: str
    content_type: str | None = None
    metadata: dict[str, str] | None = None


class SourceObjectStore(Protocol):
    def presign_post(
        self,
        object_key: str,
        *,
        content_type: str,
        sha256: str,
        size_bytes: int,
        expires_at: datetime,
    ) -> UploadPolicy: ...

    def digest(self, object_key: str, *, max_bytes: int) -> ObjectDigest: ...


@dataclass(frozen=True, slots=True)
class CreateUploadResult:
    upload_session: UploadSession
    source: Source


@dataclass(frozen=True, slots=True)
class CompleteUploadResult:
    upload_session: UploadSession
    source: Source
    accepted: bool
    rejection_code: str | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def sanitize_source_filename(value: str) -> tuple[str, str]:
    """Return a display-only basename and its normalized allow-listed extension."""
    candidate = PurePosixPath(value.replace("\\", "/")).name.strip()
    if not candidate or len(candidate) > 255 or _CONTROL.search(candidate):
        raise UploadValidationError("filename must contain 1 to 255 safe characters")
    if candidate in {".", ".."}:
        raise UploadValidationError("filename is invalid")
    extension = PurePosixPath(candidate).suffix.lower()
    if extension not in SUPPORTED_SOURCE_TYPES:
        raise UploadValidationError("only DOCX, PDF, PPTX, and HTML sources are accepted")
    return candidate, extension


def validate_upload_request(
    *, filename: str, declared_mime_type: str, expected_sha256: str, size_bytes: int
) -> tuple[str, str, str]:
    safe_filename, extension = sanitize_source_filename(filename)
    expected_type = SUPPORTED_SOURCE_TYPES[extension]
    if declared_mime_type.strip().lower() != expected_type:
        raise UploadValidationError("filename extension and declared MIME type do not match")
    normalized_sha = expected_sha256.strip()
    if not _SHA256.fullmatch(normalized_sha):
        raise UploadValidationError("expectedSha256 must be a lowercase SHA-256 digest")
    if not 1 <= size_bytes <= MAX_SOURCE_BYTES:
        raise UploadValidationError(f"sizeBytes must be between 1 and {MAX_SOURCE_BYTES} bytes")
    return safe_filename, extension, normalized_sha


def create_upload_session(
    session: Session,
    context: TenantContext,
    *,
    filename: str,
    declared_mime_type: str,
    expected_sha256: str,
    size_bytes: int,
    ttl_seconds: int,
    request_id: str,
) -> CreateUploadResult:
    if not 60 <= ttl_seconds <= 900:
        raise ValueError("upload session TTL must be between 60 and 900 seconds")
    safe_filename, extension, normalized_sha = validate_upload_request(
        filename=filename,
        declared_mime_type=declared_mime_type,
        expected_sha256=expected_sha256,
        size_bytes=size_bytes,
    )
    now = utc_now()
    source_id = new_ulid()
    upload_session_id = new_ulid()
    source = Source(
        id=source_id,
        organization_id=context.organization_id,
        original_filename=safe_filename,
        extension=extension,
        declared_mime_type=SUPPORTED_SOURCE_TYPES[extension],
        source_sha256=normalized_sha,
        size_bytes=size_bytes,
        status="uploading",
        scan_status="pending",
        parse_status="pending",
    )
    upload = UploadSession(
        id=upload_session_id,
        organization_id=context.organization_id,
        source_id=source_id,
        object_key=tenant_object_key(context.organization_id, "quarantine", upload_session_id),
        declared_mime_type=SUPPORTED_SOURCE_TYPES[extension],
        expected_sha256=normalized_sha,
        expected_size_bytes=size_bytes,
        max_bytes=size_bytes,
        status="pending",
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    session.add_all((source, upload))
    append_audit(
        session,
        context,
        resource_type="source",
        resource_id=source_id,
        action="source.upload_session.created",
        request_id=request_id,
        outcome="succeeded",
        details={"extension": extension, "sizeBytes": size_bytes},
    )
    session.flush()
    return CreateUploadResult(upload_session=upload, source=source)


def get_upload_session(
    session: Session,
    upload_session_id: str,
    organization_id: str,
    *,
    for_update: bool = False,
) -> UploadSession:
    query = select(UploadSession).where(
        UploadSession.id == upload_session_id,
        UploadSession.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise SourceNotFound("upload session does not exist")
    return row


def get_source(
    session: Session,
    source_id: str,
    organization_id: str,
    *,
    for_update: bool = False,
) -> Source:
    query = select(Source).where(
        Source.id == source_id,
        Source.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise SourceNotFound("source does not exist")
    return row


def _reject_upload(
    upload: UploadSession,
    source: Source,
    *,
    code: str,
    expired: bool = False,
) -> CompleteUploadResult:
    upload.status = "expired" if expired else "rejected"
    upload.rejection_code = code
    source.status = "rejected"
    source.error_code = code
    source.error_detail = "上传对象未通过完整性校验"
    source.retryable = False
    source.lock_version += 1
    return CompleteUploadResult(upload, source, accepted=False, rejection_code=code)


def complete_upload_session(
    session: Session,
    context: TenantContext,
    upload_session_id: str,
    *,
    digest: ObjectDigest,
    request_id: str,
) -> CompleteUploadResult:
    now = utc_now()
    upload = get_upload_session(
        session, upload_session_id, context.organization_id, for_update=True
    )
    source = get_source(session, upload.source_id, context.organization_id, for_update=True)
    if upload.status == "completed":
        return CompleteUploadResult(upload, source, accepted=True)
    if upload.status in {"expired", "rejected"}:
        return CompleteUploadResult(
            upload, source, accepted=False, rejection_code=upload.rejection_code
        )
    if upload.expires_at <= now:
        result = _reject_upload(upload, source, code="UPLOAD_SESSION_EXPIRED", expired=True)
    elif digest.size_bytes != upload.expected_size_bytes:
        result = _reject_upload(upload, source, code="UPLOAD_SIZE_MISMATCH")
    elif digest.sha256 != upload.expected_sha256:
        result = _reject_upload(upload, source, code="UPLOAD_CHECKSUM_MISMATCH")
    elif digest.content_type and digest.content_type != upload.declared_mime_type:
        result = _reject_upload(upload, source, code="UPLOAD_CONTENT_TYPE_MISMATCH")
    elif digest.metadata and digest.metadata.get("sha256") not in {
        None,
        upload.expected_sha256,
    }:
        result = _reject_upload(upload, source, code="UPLOAD_METADATA_MISMATCH")
    else:
        retention = now + timedelta(days=SOURCE_RETENTION_DAYS)
        artifact = Artifact(
            id=upload.id,
            organization_id=context.organization_id,
            artifact_type="source_input",
            partition="quarantine",
            object_key=upload.object_key,
            sha256=digest.sha256,
            media_type=upload.declared_mime_type,
            size_bytes=digest.size_bytes,
            status="pending",
            retention_expires_at=retention,
        )
        session.add(artifact)
        source.input_artifact_id = artifact.id
        source.status = "uploaded"
        source.size_bytes = digest.size_bytes
        source.uploaded_at = now
        source.lock_version += 1
        upload.status = "completed"
        upload.completed_at = now
        upload.rejection_code = None
        session.add(
            OutboxEvent(
                id=new_ulid(),
                organization_id=context.organization_id,
                kind="task",
                aggregate_type="source",
                aggregate_id=source.id,
                dedupe_key=f"source-process:{source.id}:1",
                destination="instant_ppt.process_source",
                payload={
                    "sourceId": source.id,
                    "organizationId": context.organization_id,
                    "reason": "upload_completed",
                },
                status="pending",
                available_at=now,
            )
        )
        result = CompleteUploadResult(upload, source, accepted=True)
    append_audit(
        session,
        context,
        resource_type="source",
        resource_id=source.id,
        action="source.upload.completed",
        request_id=request_id,
        outcome="succeeded" if result.accepted else "rejected",
        details={
            "sizeBytes": digest.size_bytes,
            "rejectionCode": result.rejection_code,
        },
    )
    session.flush()
    return result


def serialize_upload_session(upload: UploadSession) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "uploadSessionId": upload.id,
        "organizationId": upload.organization_id,
        "objectKey": upload.object_key,
        "declaredMimeType": upload.declared_mime_type,
        "expectedSha256": upload.expected_sha256,
        "maxBytes": upload.max_bytes,
        "expiresAt": upload.expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "status": upload.status,
    }


def serialize_source(source: Source) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "sourceId": source.id,
        "organizationId": source.organization_id,
        "filename": source.original_filename,
        "declaredMimeType": source.declared_mime_type,
        "detectedMimeType": source.detected_mime_type,
        "sourceSha256": source.source_sha256,
        "sizeBytes": source.size_bytes,
        "status": source.status,
        "scanStatus": source.scan_status,
        "parseStatus": source.parse_status,
        "scanAttempt": source.scan_attempt,
        "parseAttempt": source.parse_attempt,
        "scanDecision": source.scan_decision,
        "retryable": source.retryable,
        "errorCode": source.error_code,
        "errorDetail": source.error_detail,
        "parserVersion": source.parser_version,
        "sourcePackage": source.source_package,
        "createdAt": source.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "updatedAt": source.updated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }


def list_source_artifacts(
    session: Session, source_id: str, organization_id: str
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(SourceArtifact, Artifact)
        .join(
            Artifact,
            (Artifact.id == SourceArtifact.artifact_id)
            & (Artifact.organization_id == SourceArtifact.organization_id),
        )
        .where(
            SourceArtifact.source_id == source_id,
            SourceArtifact.organization_id == organization_id,
            Artifact.status == "published",
            Artifact.partition == "published",
        )
        .order_by(SourceArtifact.kind, SourceArtifact.id)
    ).all()
    return [
        {
            "schemaVersion": 1,
            "artifactId": artifact.id,
            "sourceId": association.source_id,
            "organizationId": association.organization_id,
            "kind": association.kind,
            "objectKey": artifact.object_key,
            "sha256": artifact.sha256,
            "mimeType": artifact.media_type,
            "sizeBytes": artifact.size_bytes,
            "parserVersion": association.parser_version,
            "createdAt": association.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
        for association, artifact in rows
    ]


def retry_source_processing(
    session: Session,
    context: TenantContext,
    source_id: str,
    *,
    request_id: str,
) -> Source:
    source = get_source(session, source_id, context.organization_id, for_update=True)
    if not source.retryable or source.status not in {"rejected", "parse_failed"}:
        raise SourceRetryRejected("source is not in a retryable failure state")
    if source.scan_status != "clean":
        if source.scan_attempt >= 5:
            source.retryable = False
            raise SourceRetryRejected("source scan retry limit has been reached")
        source.status = "uploaded"
        source.scan_status = "pending"
        attempt = source.scan_attempt + 1
        stage = "scan"
    else:
        if source.parse_attempt >= 5:
            source.retryable = False
            raise SourceRetryRejected("source parse retry limit has been reached")
        source.status = "clean"
        source.parse_status = "pending"
        attempt = source.parse_attempt + 1
        stage = "parse"
    source.error_code = None
    source.error_detail = None
    source.retryable = False
    source.lock_version += 1
    now = utc_now()
    session.add(
        OutboxEvent(
            id=new_ulid(),
            organization_id=context.organization_id,
            kind="task",
            aggregate_type="source",
            aggregate_id=source.id,
            dedupe_key=f"source-process:{source.id}:{stage}:{attempt}",
            destination="instant_ppt.process_source",
            payload={
                "sourceId": source.id,
                "organizationId": context.organization_id,
                "reason": f"user_retry_{stage}",
            },
            status="pending",
            available_at=now,
        )
    )
    append_audit(
        session,
        context,
        resource_type="source",
        resource_id=source.id,
        action="source.processing.retry_requested",
        request_id=request_id,
        outcome="succeeded",
        details={"stage": stage, "attempt": attempt},
    )
    session.flush()
    return source
