"""Build G03 runtime images and verify a user journey through real containers."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from instant_ppt_api.object_store import ObjectStoreSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.migrations import upgrade
from instant_ppt_domain.models import Artifact, ArtifactDownloadGrant, AuditLog, User
from minio import Minio
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@localhost:5432/instant_ppt"
)
API_ROOT = "http://localhost:8000"


def _run(
    command_line: list[str],
    *,
    environment: dict[str, str] | None = None,
    capture: bool = False,
) -> str:
    result = subprocess.run(
        command_line,
        cwd=ROOT,
        env=environment,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def _headers(subject: str, **extra: str) -> dict[str, str]:
    return {
        "X-Dev-User-Subject": subject,
        "X-Dev-User-Email": f"{subject}@example.test",
        "X-Dev-User-Name": subject.title(),
        **extra,
    }


def _request(
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_ROOT}{path}",
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            **headers,
        },
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def _wait_for_api(headers: dict[str, str]) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            status, _ = _request("GET", "/v1/me/entitlements", headers=headers)
            if status == 200:
                return
        except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
            pass
        time.sleep(1)
    raise RuntimeError("container API did not become ready within 90 seconds")


def _wait_for_job(job_id: str, headers: dict[str, str]) -> str:
    deadline = time.monotonic() + 90
    latest = "unknown"
    while time.monotonic() < deadline:
        status, body = _request("GET", f"/v1/jobs/{job_id}", headers=headers)
        assert status == 200
        latest = str(body["data"]["status"])  # type: ignore[index]
        if latest in {"succeeded", "partially_succeeded", "failed", "cancelled"}:
            return latest
        time.sleep(0.5)
    raise RuntimeError(f"container job did not finish; latest status={latest}")


def _verify_journey() -> dict[str, object]:
    alice_headers = _headers("container-e2e-alice")
    bob_headers = _headers("container-e2e-bob")
    secret_canary = "Bearer g03-container-secret-canary"
    status, alice_entitlements = _request(
        "GET",
        "/v1/me/entitlements",
        headers={**alice_headers, "Authorization": secret_canary},
    )
    assert status == 200
    status, bob_entitlements = _request(
        "GET", "/v1/me/entitlements", headers=bob_headers
    )
    assert status == 200
    alice_org = str(alice_entitlements["resourceId"])
    bob_org = str(bob_entitlements["resourceId"])
    assert alice_org != bob_org
    assert alice_entitlements["data"]["planCode"] == "p1-default"  # type: ignore[index]

    job_payload = {
        "schemaVersion": 1,
        "data": {"slideCount": 2, "failureModes": {}, "stepDelayMs": 10},
        "baseRevisionId": None,
    }
    status, job = _request(
        "POST",
        "/v1/drafts/01ARZ3NDEKTSV4RRFFQ69G5FAC/generation-jobs",
        headers={**alice_headers, "Idempotency-Key": f"container-job-{new_ulid()}"},
        payload=job_payload,
    )
    assert status == 202
    job_id = str(job["resourceId"])
    assert _request("GET", f"/v1/jobs/{job_id}", headers=bob_headers)[0] == 404
    assert _wait_for_job(job_id, alice_headers) == "succeeded"

    store_settings = ObjectStoreSettings(
        endpoint="http://localhost:9000",
        public_endpoint="http://localhost:9000",
        region="us-east-1",
        access_key="instant-ppt-local",
        secret_key="local-development-only",
        bucket="instant-ppt-private",
    )
    minio = Minio(
        "localhost:9000",
        access_key=store_settings.access_key,
        secret_key=store_settings.secret_key,
        secure=False,
        region=store_settings.region,
    )
    if not minio.bucket_exists(store_settings.bucket):
        minio.make_bucket(store_settings.bucket)
    artifact_id = new_ulid()
    object_key = f"tenants/{alice_org}/published/{artifact_id}"
    content = b"g03-container-private-object-canary"
    minio.put_object(
        store_settings.bucket,
        object_key,
        io.BytesIO(content),
        len(content),
        content_type="application/octet-stream",
    )
    engine = create_domain_engine(DATABASE_URL)
    factory = create_session_factory(engine)
    try:
        with factory.begin() as session:
            alice = session.scalar(
                select(User).where(User.subject == "container-e2e-alice")
            )
            assert alice is not None
            session.add(
                Artifact(
                    id=artifact_id,
                    organization_id=alice_org,
                    artifact_type="container_fixture",
                    partition="published",
                    object_key=object_key,
                    sha256=hashlib.sha256(content).hexdigest(),
                    media_type="application/octet-stream",
                    size_bytes=len(content),
                    status="published",
                    retention_expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        mutation = {"schemaVersion": 1, "data": {}}
        status, authorized = _request(
            "POST",
            f"/v1/artifacts/{artifact_id}:authorize-download",
            headers={
                **alice_headers,
                "Idempotency-Key": f"container-download-{new_ulid()}",
            },
            payload=mutation,
        )
        assert status == 200
        download_url = str(authorized["data"]["downloadUrl"])  # type: ignore[index]
        with urlopen(download_url, timeout=10) as response:  # noqa: S310
            assert response.read() == content
        assert (
            _request(
                "POST",
                f"/v1/artifacts/{artifact_id}:authorize-download",
                headers={
                    **bob_headers,
                    "Idempotency-Key": f"container-theft-{new_ulid()}",
                },
                payload=mutation,
            )[0]
            == 404
        )
        with factory() as session:
            assert (
                session.scalar(
                    select(func.count()).select_from(ArtifactDownloadGrant).where(
                        ArtifactDownloadGrant.organization_id == alice_org,
                        ArtifactDownloadGrant.artifact_id == artifact_id,
                    )
                )
                == 1
            )
            audit = session.scalar(
                select(AuditLog).where(
                    AuditLog.organization_id == alice_org,
                    AuditLog.resource_id == artifact_id,
                    AuditLog.action == "artifact.download.authorized",
                )
            )
            assert audit is not None
            assert audit.actor_id == alice.id
            assert audit.request_id
            assert "http" not in str(audit.details)
    finally:
        engine.dispose()
        minio.remove_object(store_settings.bucket, object_key)

    logs = _run(["docker", "compose", "logs", "--no-color", "api"], capture=True)
    assert secret_canary not in logs
    assert "container-e2e-alice@example.test" not in logs
    assert "X-Amz-Signature" not in logs
    assert content.decode() not in logs
    return {
        "aliceOrganizationId": alice_org,
        "bobOrganizationId": bob_org,
        "jobId": job_id,
        "jobStatus": "succeeded",
        "artifactId": artifact_id,
        "download": "signed bytes matched; cross-tenant denied",
        "logRedaction": "passed",
    }


def main() -> None:
    environment = os.environ.copy()
    environment["COMPOSE_BAKE"] = "false"
    environment.update(
        {
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_PUBLIC_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "instant-ppt-local",
            "S3_SECRET_KEY": "local-development-only",
            "S3_BUCKET": "instant-ppt-private",
            "APP_ENVIRONMENT": "local",
            "AUTH_MODE": "local",
        }
    )
    _run(
        [
            "docker",
            "compose",
            "up",
            "--wait",
            "--wait-timeout",
            "90",
            "postgres",
            "redis",
            "minio",
        ],
        environment=environment,
    )
    upgrade(DATABASE_URL)
    for service in ("api", "worker", "outbox"):
        _run(["docker", "compose", "build", service], environment=environment)
    _run(
        [
            "docker",
            "compose",
            "--profile",
            "runtime",
            "up",
            "-d",
            "--force-recreate",
            "api",
            "worker",
            "outbox",
        ],
        environment=environment,
    )
    started_at = datetime.now(UTC)
    try:
        _wait_for_api(_headers("container-e2e-alice"))
        user_ids = {
            service: _run(
                ["docker", "compose", "exec", "-T", service, "id", "-u"],
                environment=environment,
                capture=True,
            )
            for service in ("api", "worker", "outbox")
        }
        assert user_ids == {"api": "10001", "worker": "10001", "outbox": "10001"}
        journey = _verify_journey()
        evidence = {
            "schemaVersion": 1,
            "goal": "G03",
            "startedAt": started_at.isoformat().replace("+00:00", "Z"),
            "completedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": "passed",
            "runtimeUserIds": user_ids,
            "services": ["api", "worker", "outbox", "postgres", "redis", "minio"],
            "journey": journey,
        }
        target = ROOT / "docs" / "evidence" / "security" / "g03-container-e2e.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("G03 container user journey passed")
    finally:
        _run(
            ["docker", "compose", "stop", "api", "worker", "outbox"],
            environment=environment,
        )


if __name__ == "__main__":
    main()
