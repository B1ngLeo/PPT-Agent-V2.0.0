from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from instant_ppt_domain.artifacts import tenant_object_key
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    ArtifactDownloadGrant,
    AuditLog,
    IdempotencyRecord,
    User,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .helpers import MemoryObjectStore, identity_headers


def _create_artifact(
    session_factory: sessionmaker[Session],
    store: MemoryObjectStore,
    *,
    subject: str,
    organization_id: str,
    object_key_override: str | None = None,
    expired: bool = False,
) -> str:
    artifact_id = new_ulid()
    content = b"private-pptx-fixture"
    object_key = object_key_override or tenant_object_key(
        organization_id, "published", artifact_id
    )
    store.objects[object_key] = content
    with session_factory.begin() as session:
        user = session.scalar(select(User).where(User.subject == subject))
        assert user is not None
        session.add(
            Artifact(
                id=artifact_id,
                organization_id=organization_id,
                artifact_type="export_pptx",
                partition="published",
                object_key=object_key,
                sha256="a" * 64,
                media_type=(
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
                size_bytes=len(content),
                status="published",
                retention_expires_at=datetime.now(UTC)
                + (timedelta(seconds=-1) if expired else timedelta(days=1)),
            )
        )
    return artifact_id


def test_private_download_authorization_is_tenant_scoped_and_idempotent(
    client: TestClient,
    session_factory: sessionmaker[Session],
    memory_store: MemoryObjectStore,
) -> None:
    alice_headers = identity_headers("artifact-alice")
    bob_headers = identity_headers("artifact-bob")
    alice_org = client.get("/v1/me/entitlements", headers=alice_headers).json()[
        "resourceId"
    ]
    client.get("/v1/me/entitlements", headers=bob_headers)
    artifact_id = _create_artifact(
        session_factory,
        memory_store,
        subject="artifact-alice",
        organization_id=alice_org,
    )
    path = f"/v1/artifacts/{artifact_id}:authorize-download"
    mutation = {"schemaVersion": 1, "data": {}, "baseRevisionId": None}
    first = client.post(
        path,
        headers={**alice_headers, "Idempotency-Key": "download-one"},
        json=mutation,
    )
    replay = client.post(
        path,
        headers={**alice_headers, "Idempotency-Key": "download-one"},
        json=mutation,
    )
    assert first.status_code == replay.status_code == 200
    assert first.json()["data"]["expiresAt"] == replay.json()["data"]["expiresAt"]
    assert "downloadUrl" in replay.json()["data"]
    assert replay.headers["idempotency-replayed"] == "true"
    assert "X-Amz-Expires=15" in first.json()["data"]["downloadUrl"]
    assert client.post(
        path,
        headers={**bob_headers, "Idempotency-Key": "stolen-artifact"},
        json=mutation,
    ).status_code == 404
    conflict = client.post(
        path,
        headers={**alice_headers, "Idempotency-Key": "download-one"},
        json={"schemaVersion": 1, "data": {"changed": True}},
    )
    assert conflict.status_code == 409
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(ArtifactDownloadGrant)) == 1
        )
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "artifact.download.authorized")
        )
        assert audit is not None
        assert audit.organization_id == alice_org
        assert "url" not in str(audit.details).lower()
        artifact = session.get(Artifact, artifact_id)
        assert artifact is not None
        assert "http" not in artifact.object_key
        idempotency = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.idempotency_key == "download-one"
            )
        )
        assert idempotency is not None
        assert "downloadUrl" not in idempotency.response_body["data"]
        assert "http" not in str(idempotency.response_body)


def test_expired_idempotent_authorization_requires_a_new_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
    memory_store: MemoryObjectStore,
) -> None:
    headers = identity_headers("expired-replay-owner")
    organization_id = client.get("/v1/me/entitlements", headers=headers).json()[
        "resourceId"
    ]
    artifact_id = _create_artifact(
        session_factory,
        memory_store,
        subject="expired-replay-owner",
        organization_id=organization_id,
    )
    path = f"/v1/artifacts/{artifact_id}:authorize-download"
    mutation = {"schemaVersion": 1, "data": {}}
    first = client.post(
        path,
        headers={**headers, "Idempotency-Key": "eventually-expired"},
        json=mutation,
    )
    assert first.status_code == 200
    with session_factory.begin() as session:
        record = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.idempotency_key == "eventually-expired"
            )
        )
        assert record is not None
        record.response_body = {
            **record.response_body,
            "data": {
                "expiresAt": (
                    datetime.now(UTC) - timedelta(seconds=1)
                ).isoformat().replace("+00:00", "Z")
            },
        }
    expired = client.post(
        path,
        headers={**headers, "Idempotency-Key": "eventually-expired"},
        json=mutation,
    )
    assert expired.status_code == 410
    assert expired.json()["code"] == "download_authorization_expired"
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(ArtifactDownloadGrant)) == 1
        )


def test_expired_or_wrong_partition_artifact_fails_closed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    memory_store: MemoryObjectStore,
) -> None:
    headers = identity_headers("artifact-owner")
    organization_id = client.get("/v1/me/entitlements", headers=headers).json()[
        "resourceId"
    ]
    expired_id = _create_artifact(
        session_factory,
        memory_store,
        subject="artifact-owner",
        organization_id=organization_id,
        expired=True,
    )
    wrong_key_id = _create_artifact(
        session_factory,
        memory_store,
        subject="artifact-owner",
        organization_id=organization_id,
        object_key_override="tenants/01ARZ3NDEKTSV4RRFFQ69G5FZZ/published/foreign",
    )
    mutation = {"schemaVersion": 1, "data": {}}
    assert client.post(
        f"/v1/artifacts/{expired_id}:authorize-download",
        headers={**headers, "Idempotency-Key": "expired"},
        json=mutation,
    ).status_code == 404
    mismatch = client.post(
        f"/v1/artifacts/{wrong_key_id}:authorize-download",
        headers={**headers, "Idempotency-Key": "wrong-key"},
        json=mutation,
    )
    assert mismatch.status_code == 503
    assert mismatch.json()["retryable"] is True


def test_request_logging_excludes_headers_content_and_signed_urls(
    client: TestClient, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="instant_ppt_api.request")
    secret = "Bearer secret-that-must-never-appear"
    response = client.get(
        "/v1/me/entitlements",
        headers={**identity_headers("log-user"), "Authorization": secret},
    )
    assert response.status_code == 200
    logs = caplog.text
    assert secret not in logs
    assert "log-user@example.test" not in logs
    assert "Authorization" not in logs
    assert "X-Amz-Signature" not in logs
