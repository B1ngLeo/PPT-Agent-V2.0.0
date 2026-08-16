"""Tenant-safe artifact metadata and short-lived download authorization."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import Artifact, ArtifactDownloadGrant
from instant_ppt_domain.tenancy import TenantContext, append_audit

ALLOWED_PARTITIONS = frozenset({"quarantine", "clean", "tmp", "published"})


class ArtifactNotFound(LookupError):
    pass


class ArtifactUnavailable(RuntimeError):
    pass


class DownloadAuthorizationExpired(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ObjectStat:
    size_bytes: int
    etag: str | None = None


class PrivateObjectStore(Protocol):
    def stat(self, object_key: str) -> ObjectStat: ...

    def presign_get(self, object_key: str, *, expires: timedelta) -> str: ...


@dataclass(frozen=True, slots=True)
class DownloadAuthorization:
    artifact_id: str
    url: str
    expires_at: datetime


def tenant_object_key(organization_id: str, partition: str, artifact_id: str) -> str:
    if partition not in ALLOWED_PARTITIONS:
        raise ValueError("invalid object partition")
    for value in (organization_id, artifact_id):
        if len(value) != 26 or "/" in value or "\\" in value or ".." in value:
            raise ValueError("organization and artifact identifiers must be ULIDs")
    return f"tenants/{organization_id}/{partition}/{artifact_id}"


def authorize_download(
    session: Session,
    context: TenantContext,
    artifact_id: str,
    *,
    object_store: PrivateObjectStore,
    request_id: str,
    ttl_seconds: int,
) -> DownloadAuthorization:
    if not 15 <= ttl_seconds <= 900:
        raise ValueError("download URL TTL must be between 15 and 900 seconds")
    now = datetime.now(UTC)
    artifact = session.scalar(
        select(Artifact)
        .where(
            Artifact.id == artifact_id,
            Artifact.organization_id == context.organization_id,
            Artifact.status == "published",
            Artifact.partition == "published",
            Artifact.revoked_at.is_(None),
            Artifact.deleted_at.is_(None),
            Artifact.retention_expires_at > now,
        )
        .with_for_update()
    )
    if artifact is None:
        raise ArtifactNotFound("artifact does not exist or is not accessible")
    expected_key = tenant_object_key(context.organization_id, artifact.partition, artifact.id)
    if artifact.object_key != expected_key:
        raise ArtifactUnavailable("artifact object key violates the tenant partition")
    stat = object_store.stat(artifact.object_key)
    if stat.size_bytes != artifact.size_bytes:
        raise ArtifactUnavailable("artifact metadata does not match object storage")
    expires_at = now + timedelta(seconds=ttl_seconds)
    url = object_store.presign_get(artifact.object_key, expires=timedelta(seconds=ttl_seconds))
    session.add(
        ArtifactDownloadGrant(
            id=new_ulid(),
            organization_id=context.organization_id,
            artifact_id=artifact.id,
            user_id=context.user_id,
            request_id=request_id,
            expires_at=expires_at,
        )
    )
    append_audit(
        session,
        context,
        resource_type="artifact",
        resource_id=artifact.id,
        action="artifact.download.authorized",
        request_id=request_id,
        outcome="succeeded",
        details={"ttlSeconds": ttl_seconds, "partition": artifact.partition},
    )
    return DownloadAuthorization(artifact_id=artifact.id, url=url, expires_at=expires_at)


def replay_download_authorization(
    session: Session,
    context: TenantContext,
    artifact_id: str,
    *,
    object_store: PrivateObjectStore,
    expires_at: datetime,
) -> DownloadAuthorization:
    """Re-sign an idempotent replay without extending or duplicating its grant."""
    now = datetime.now(UTC)
    remaining_seconds = math.ceil((expires_at - now).total_seconds())
    if remaining_seconds <= 0:
        raise DownloadAuthorizationExpired("download authorization has expired")
    artifact = session.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.organization_id == context.organization_id,
            Artifact.status == "published",
            Artifact.partition == "published",
            Artifact.revoked_at.is_(None),
            Artifact.deleted_at.is_(None),
            Artifact.retention_expires_at > now,
        )
    )
    if artifact is None:
        raise ArtifactNotFound("artifact does not exist or is not accessible")
    expected_key = tenant_object_key(context.organization_id, artifact.partition, artifact.id)
    if artifact.object_key != expected_key:
        raise ArtifactUnavailable("artifact object key violates the tenant partition")
    stat = object_store.stat(artifact.object_key)
    if stat.size_bytes != artifact.size_bytes:
        raise ArtifactUnavailable("artifact metadata does not match object storage")
    url = object_store.presign_get(
        artifact.object_key, expires=timedelta(seconds=remaining_seconds)
    )
    return DownloadAuthorization(
        artifact_id=artifact.id,
        url=url,
        expires_at=expires_at,
    )
