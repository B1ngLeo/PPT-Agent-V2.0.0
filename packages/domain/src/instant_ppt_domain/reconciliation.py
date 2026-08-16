"""Repair or alert on database/object-store publication divergence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    ObjectReconciliationRun,
    UploadSession,
)


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_key: str
    last_modified: datetime


class ReconciliationObjectStore(Protocol):
    def list_objects(self, prefix: str) -> Iterable[StoredObject]: ...

    def remove(self, object_key: str) -> None: ...


def _mark_failed(
    factory: sessionmaker[Session], run_id: str, error_code: str, now: datetime
) -> None:
    with factory.begin() as session:
        run = session.get(ObjectReconciliationRun, run_id, with_for_update=True)
        if run is not None:
            run.status = "failed"
            run.error_code = error_code[:80]
            run.terminal_at = now


def reconcile_organization_objects(
    factory: sessionmaker[Session],
    store: ReconciliationObjectStore,
    organization_id: str,
    *,
    dry_run: bool = False,
    orphan_grace_seconds: int = 3600,
    now: datetime | None = None,
) -> dict[str, object]:
    """Reconcile one tenant; deletion is bounded to its ULID-only object prefix."""
    observed_at = now or datetime.now(UTC)
    run_id = new_ulid()
    with factory.begin() as session:
        session.add(
            ObjectReconciliationRun(
                id=run_id,
                organization_id=organization_id,
                status="running",
                dry_run=dry_run,
                result={},
            )
        )

    try:
        prefix = f"tenants/{organization_id}/"
        stored = {item.object_key: item for item in store.list_objects(prefix)}
        if any(not key.startswith(prefix) for key in stored):
            raise ValueError("object store returned a key outside the tenant prefix")

        with factory.begin() as session:
            artifacts = list(
                session.scalars(
                    select(Artifact).where(Artifact.organization_id == organization_id)
                )
            )
            uploads = list(
                session.scalars(
                    select(UploadSession).where(
                        UploadSession.organization_id == organization_id,
                        UploadSession.status.in_(("pending", "uploaded")),
                        UploadSession.expires_at > observed_at,
                    )
                )
            )
            active_artifacts = {
                row.object_key: row
                for row in artifacts
                if row.deleted_at is None and row.status != "deleted"
            }
            protected_upload_keys = {row.object_key for row in uploads}
            missing_keys = sorted(set(active_artifacts) - set(stored))
            expired_keys = sorted(
                key
                for key, row in active_artifacts.items()
                if row.retention_expires_at <= observed_at and key in stored
            )
            orphan_cutoff = observed_at - timedelta(seconds=max(0, orphan_grace_seconds))
            orphan_keys = sorted(
                key
                for key, item in stored.items()
                if key not in active_artifacts
                and key not in protected_upload_keys
                and item.last_modified <= orphan_cutoff
            )

            removed_keys: list[str] = []
            failed_removals: list[str] = []
            for key in sorted(set(expired_keys + orphan_keys)):
                if dry_run:
                    continue
                try:
                    store.remove(key)
                    removed_keys.append(key)
                except Exception:  # store adapter normalizes provider details
                    failed_removals.append(key)

            missing_published = 0
            if not dry_run:
                for key in sorted(set(missing_keys + expired_keys)):
                    artifact = active_artifacts[key]
                    if artifact.status == "published" and key in missing_keys:
                        missing_published += 1
                    if key in missing_keys or key in removed_keys:
                        artifact.status = "deleted"
                        artifact.revoked_at = artifact.revoked_at or observed_at
                        artifact.deleted_at = observed_at

            result: dict[str, object] = {
                "runId": run_id,
                "organizationId": organization_id,
                "dryRun": dry_run,
                "databaseArtifactCount": len(artifacts),
                "objectCount": len(stored),
                "protectedUploadCount": len(protected_upload_keys),
                "missingObjectCount": len(missing_keys),
                "missingPublishedCount": missing_published,
                "expiredObjectCount": len(expired_keys),
                "orphanObjectCount": len(orphan_keys),
                "removedObjectCount": len(removed_keys),
                "failedRemovalCount": len(failed_removals),
                "alertCount": len(missing_keys) + len(failed_removals),
                "missingObjectKeys": missing_keys,
                "orphanObjectKeys": orphan_keys,
                "failedRemovalKeys": failed_removals,
            }
            run = session.get(ObjectReconciliationRun, run_id, with_for_update=True)
            assert run is not None
            run.result = result
            run.status = (
                "succeeded_with_alerts" if result["alertCount"] else "succeeded"
            )
            run.terminal_at = observed_at
            return result
    except Exception as error:
        _mark_failed(factory, run_id, type(error).__name__, observed_at)
        raise
