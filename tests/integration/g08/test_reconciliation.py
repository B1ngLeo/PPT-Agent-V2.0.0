from __future__ import annotations

from datetime import UTC, datetime, timedelta

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    ObjectReconciliationRun,
    Organization,
    Source,
    UploadSession,
)
from instant_ppt_domain.reconciliation import reconcile_organization_objects
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.g08.conftest import ReconciliationStore


def _organization(session_factory: sessionmaker[Session]) -> str:
    organization_id = new_ulid()
    with session_factory.begin() as session:
        session.add(
            Organization(
                id=organization_id,
                kind="personal",
                name="G08 reconciliation tenant",
                slug=f"g08-{organization_id.lower()}",
            )
        )
    return organization_id


def _artifact(
    session_factory: sessionmaker[Session],
    organization_id: str,
    object_key: str,
    *,
    retention_expires_at: datetime,
) -> str:
    artifact_id = new_ulid()
    with session_factory.begin() as session:
        session.add(
            Artifact(
                id=artifact_id,
                organization_id=organization_id,
                artifact_type="generation_manifest",
                partition="published",
                object_key=object_key,
                sha256="1" * 64,
                media_type="application/json",
                size_bytes=2,
                status="published",
                retention_expires_at=retention_expires_at,
            )
        )
    return artifact_id


def test_clean_reconciliation_protects_active_uploads(
    session_factory: sessionmaker[Session], object_store: ReconciliationStore
) -> None:
    now = datetime.now(UTC)
    organization_id = _organization(session_factory)
    artifact_key = f"tenants/{organization_id}/published/artifact"
    upload_key = f"tenants/{organization_id}/quarantine/upload"
    _artifact(
        session_factory,
        organization_id,
        artifact_key,
        retention_expires_at=now + timedelta(days=1),
    )
    source_id = new_ulid()
    with session_factory.begin() as session:
        session.add(
            Source(
                id=source_id,
                organization_id=organization_id,
                original_filename="upload.docx",
                declared_mime_type=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                extension=".docx",
                source_sha256="2" * 64,
                size_bytes=2,
                status="uploading",
            )
        )
        session.flush()
        session.add(
            UploadSession(
                id=new_ulid(),
                organization_id=organization_id,
                source_id=source_id,
                object_key=upload_key,
                declared_mime_type=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                expected_sha256="2" * 64,
                expected_size_bytes=2,
                max_bytes=50 * 1024 * 1024,
                status="pending",
                expires_at=now + timedelta(minutes=10),
            )
        )
    object_store.add(artifact_key, modified_at=now - timedelta(hours=2))
    object_store.add(upload_key, modified_at=now - timedelta(hours=2))
    result = reconcile_organization_objects(
        session_factory, object_store, organization_id, now=now, orphan_grace_seconds=0
    )
    assert result["alertCount"] == 0
    assert result["protectedUploadCount"] == 1
    assert result["removedObjectCount"] == 0
    assert upload_key in object_store.objects


def test_missing_expired_and_orphan_divergence_is_repaired_or_alerted_ten_times(
    session_factory: sessionmaker[Session], object_store: ReconciliationStore
) -> None:
    now = datetime.now(UTC)
    run_ids: set[str] = set()
    for iteration in range(10):
        organization_id = _organization(session_factory)
        missing_key = f"tenants/{organization_id}/published/missing"
        expired_key = f"tenants/{organization_id}/tmp/expired"
        orphan_key = f"tenants/{organization_id}/published/orphan"
        missing_id = _artifact(
            session_factory,
            organization_id,
            missing_key,
            retention_expires_at=now + timedelta(days=1),
        )
        expired_id = _artifact(
            session_factory,
            organization_id,
            expired_key,
            retention_expires_at=now - timedelta(seconds=1),
        )
        object_store.add(expired_key, modified_at=now - timedelta(hours=2))
        object_store.add(orphan_key, modified_at=now - timedelta(hours=2))

        result = reconcile_organization_objects(
            session_factory,
            object_store,
            organization_id,
            now=now + timedelta(seconds=iteration),
            orphan_grace_seconds=0,
        )
        run_ids.add(str(result["runId"]))
        assert result["missingObjectCount"] == 1
        assert result["missingPublishedCount"] == 1
        assert result["expiredObjectCount"] == 1
        assert result["orphanObjectCount"] == 1
        assert result["removedObjectCount"] == 2
        assert result["failedRemovalCount"] == 0
        assert orphan_key not in object_store.objects
        with session_factory() as session:
            assert session.get(Artifact, missing_id).status == "deleted"
            assert session.get(Artifact, expired_id).status == "deleted"
            run = session.get(ObjectReconciliationRun, result["runId"])
            assert run.status == "succeeded_with_alerts"
    assert len(run_ids) == 10


def test_dry_run_and_failed_removal_are_auditable(
    session_factory: sessionmaker[Session], object_store: ReconciliationStore
) -> None:
    now = datetime.now(UTC)
    organization_id = _organization(session_factory)
    orphan_key = f"tenants/{organization_id}/published/orphan"
    object_store.add(orphan_key, modified_at=now - timedelta(hours=2))
    dry = reconcile_organization_objects(
        session_factory,
        object_store,
        organization_id,
        dry_run=True,
        now=now,
        orphan_grace_seconds=0,
    )
    assert dry["orphanObjectCount"] == 1
    assert dry["removedObjectCount"] == 0
    assert orphan_key in object_store.objects

    object_store.failed_removals.add(orphan_key)
    failed = reconcile_organization_objects(
        session_factory,
        object_store,
        organization_id,
        now=now,
        orphan_grace_seconds=0,
    )
    assert failed["failedRemovalCount"] == 1
    assert failed["alertCount"] == 1
    with session_factory() as session:
        assert session.scalar(select(func.count(ObjectReconciliationRun.id))) == 2
