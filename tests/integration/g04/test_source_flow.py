from __future__ import annotations

import hashlib
import socket
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread

import httpx
import pytest
from fastapi.testclient import TestClient
from instant_ppt_api.main import create_app
from instant_ppt_api.object_store import MinioPrivateObjectStore, ObjectStoreSettings
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.models import OutboxEvent, Source, SourceArtifact
from instant_ppt_worker.source_pipeline import (
    ClamAvSettings,
    ScannerUnavailable,
    WorkerObjectSettings,
    WorkerObjectStore,
    process_source_pipeline,
)
from minio.deleteobjects import DeleteObject
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[3]
DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@localhost:5432/"
    "instant_ppt_g04_test"
)
BUCKET = "instant-ppt-g04-test"
MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
}
VALID_FIXTURES = (
    ROOT / "tests/golden/08-dense-docx/source/input.docx",
    ROOT / "tests/golden/09-pdf-baseline/source/input.pdf",
    ROOT / "tests/golden/10-multilingual-pptx/source/input.pptx",
    ROOT / "tests/golden/07-template-brand/source/input.html",
)


def _headers(subject: str) -> dict[str, str]:
    return {
        "X-Dev-User-Subject": subject,
        "X-Dev-User-Email": f"{subject}@example.test",
        "X-Dev-User-Name": subject,
    }


@dataclass(slots=True)
class Uploaded:
    subject: str
    session_id: str
    source_id: str
    object_key: str
    complete_status: int


class FakeClamd:
    def __init__(self) -> None:
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._listener.settimeout(0.2)
        self.port = self._listener.getsockname()[1]
        self._stop = Event()
        self._thread = Thread(target=self._run, daemon=True)

    def __enter__(self) -> FakeClamd:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._listener.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            with connection:
                if connection.recv(len(b"zINSTREAM\0")) != b"zINSTREAM\0":
                    continue
                payload = bytearray()
                while True:
                    raw_size = _read_exact(connection, 4)
                    if len(raw_size) != 4:
                        break
                    size = struct.unpack(">I", raw_size)[0]
                    if size == 0:
                        break
                    payload.extend(_read_exact(connection, size))
                if b"CLAMAV-FOUND-MARKER" in payload:
                    connection.sendall(b"stream: Integration-Test-Signature FOUND\0")
                else:
                    connection.sendall(b"stream: OK\0")


def _read_exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        block = connection.recv(size - len(data))
        if not block:
            break
        data.extend(block)
    return bytes(data)


@pytest.fixture(scope="session")
def runtime() -> Iterator[dict[str, object]]:
    engine = create_domain_engine(DATABASE_URL)
    factory = create_session_factory(engine)
    settings = DomainSettings(
        database_url=DATABASE_URL,
        redis_events_url="redis://localhost:6379/14",
        celery_broker_url="redis://localhost:6379/15",
        sse_heartbeat_seconds=0.1,
        outbox_poll_seconds=0.05,
        worker_lease_seconds=10,
        app_environment="test",
        auth_mode="local",
        upload_session_ttl_seconds=600,
    )
    object_settings = ObjectStoreSettings(
        endpoint="http://localhost:9000",
        public_endpoint="http://localhost:9000",
        region="us-east-1",
        access_key="instant-ppt-local",
        secret_key="local-development-only",
        bucket=BUCKET,
    )
    api_store = MinioPrivateObjectStore(object_settings)
    api_store.ensure_private_bucket()
    errors = api_store._client.remove_objects(  # noqa: SLF001
        BUCKET,
        (
            DeleteObject(item.object_name)
            for item in api_store._client.list_objects(BUCKET, recursive=True)  # noqa: SLF001
        ),
    )
    assert list(errors) == []
    worker_store = WorkerObjectStore(
        WorkerObjectSettings(
            endpoint="http://localhost:9000",
            region="us-east-1",
            access_key="instant-ppt-local",
            secret_key="local-development-only",
            bucket=BUCKET,
        )
    )
    app = create_app(
        settings=settings,
        session_factory=factory,
        object_store=api_store,
    )
    with TestClient(app) as client, FakeClamd() as clamd:
        yield {
            "client": client,
            "factory": factory,
            "settings": settings,
            "api_store": api_store,
            "worker_store": worker_store,
            "clamav": ClamAvSettings(
                host="127.0.0.1", port=clamd.port, timeout_seconds=2
            ),
        }
    engine.dispose()


def _upload(
    runtime: dict[str, object],
    *,
    subject: str,
    filename: str,
    content: bytes,
    expected_sha256: str | None = None,
    idempotency_key: str | None = None,
) -> Uploaded:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    mime_type = MIME_TYPES[Path(filename).suffix.lower()]
    digest = expected_sha256 or hashlib.sha256(content).hexdigest()
    key = idempotency_key or f"create-{subject}-{hashlib.sha256(content).hexdigest()[:12]}"
    response = client.post(
        "/v1/upload-sessions",
        headers={**_headers(subject), "Idempotency-Key": key},
        json={
            "schemaVersion": 1,
            "data": {
                "filename": filename,
                "declaredMimeType": mime_type,
                "expectedSha256": digest,
                "sizeBytes": len(content),
            },
            "baseRevisionId": None,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    uploaded = httpx.post(
        data["uploadUrl"],
        data=data["formFields"],
        files={"file": (filename, content, mime_type)},
        timeout=30,
    )
    assert uploaded.status_code in {200, 204}, uploaded.text
    complete = client.post(
        f"/v1/upload-sessions/{data['uploadSessionId']}:complete",
        headers={
            **_headers(subject),
            "Idempotency-Key": f"complete-{key}",
        },
        json={"schemaVersion": 1, "data": {}, "baseRevisionId": None},
    )
    return Uploaded(
        subject=subject,
        session_id=data["uploadSessionId"],
        source_id=data["sourceId"],
        object_key=data["objectKey"],
        complete_status=complete.status_code,
    )


@pytest.mark.parametrize("fixture", VALID_FIXTURES, ids=lambda value: value.suffix)
def test_four_valid_formats_parse_and_publish(
    runtime: dict[str, object], fixture: Path
) -> None:
    content = fixture.read_bytes()
    uploaded = _upload(
        runtime,
        subject=f"valid-{fixture.suffix[1:]}",
        filename=f"private-name-{fixture.suffix[1:]}{fixture.suffix}",
        content=content,
    )
    assert uploaded.complete_status == 202
    assert "private-name" not in uploaded.object_key
    api_store: MinioPrivateObjectStore = runtime["api_store"]  # type: ignore[assignment]
    assert api_store.stat(uploaded.object_key).size_bytes == len(content)
    factory = runtime["factory"]
    with factory() as session:  # type: ignore[operator]
        source = session.get(Source, uploaded.source_id)
        assert source is not None and source.status == "uploaded"
        organization_id = source.organization_id
    assert process_source_pipeline(
        factory,  # type: ignore[arg-type]
        uploaded.source_id,
        organization_id,
        object_store=runtime["worker_store"],  # type: ignore[arg-type]
        clamav=runtime["clamav"],  # type: ignore[arg-type]
    ) == "parsed"
    response = runtime["client"].get(  # type: ignore[union-attr]
        f"/v1/sources/{uploaded.source_id}", headers=_headers(uploaded.subject)
    )
    assert response.status_code == 200
    source_data = response.json()["data"]
    assert source_data["status"] == "parsed"
    assert source_data["scanStatus"] == "clean"
    assert source_data["parseStatus"] == "succeeded"
    assert source_data["parserVersion"].startswith("source-parser@")
    assert {item["kind"] for item in source_data["artifacts"]} >= {
        "markdown",
        "conversion_profile",
    }
    for artifact in source_data["artifacts"]:
        stat = api_store.stat(artifact["objectKey"])
        assert stat.size_bytes == artifact["sizeBytes"]


def test_upload_checksum_mismatch_is_persistently_rejected(
    runtime: dict[str, object]
) -> None:
    content = b"<html><body>actual</body></html>"
    wrong = hashlib.sha256(b"<html><body>other!</body></html>").hexdigest()
    uploaded = _upload(
        runtime,
        subject="checksum-mismatch",
        filename="report.html",
        content=content,
        expected_sha256=wrong,
    )
    assert uploaded.complete_status == 422
    response = runtime["client"].get(  # type: ignore[union-attr]
        f"/v1/sources/{uploaded.source_id}", headers=_headers(uploaded.subject)
    )
    assert response.json()["data"]["errorCode"] == "UPLOAD_CHECKSUM_MISMATCH"


def test_scanner_unavailable_fails_closed_and_retry_is_idempotent(
    runtime: dict[str, object]
) -> None:
    uploaded = _upload(
        runtime,
        subject="scanner-down",
        filename="safe.html",
        content=b"<html><body>safe</body></html>",
    )
    factory = runtime["factory"]
    with factory() as session:  # type: ignore[operator]
        source = session.get(Source, uploaded.source_id)
        assert source is not None
        organization_id = source.organization_id
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        unused_port = listener.getsockname()[1]
    with pytest.raises(ScannerUnavailable):
        process_source_pipeline(
            factory,  # type: ignore[arg-type]
            uploaded.source_id,
            organization_id,
            object_store=runtime["worker_store"],  # type: ignore[arg-type]
            clamav=ClamAvSettings(
                host="127.0.0.1", port=unused_port, timeout_seconds=0.25
            ),
        )
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    status = client.get(
        f"/v1/sources/{uploaded.source_id}", headers=_headers(uploaded.subject)
    ).json()["data"]
    assert status["status"] == "rejected"
    assert status["scanStatus"] == "failed"
    assert status["retryable"] is True
    assert status["artifacts"] == []
    request = {"schemaVersion": 1, "data": {}, "baseRevisionId": None}
    headers = {**_headers(uploaded.subject), "Idempotency-Key": "retry-scanner"}
    first = client.post(
        f"/v1/sources/{uploaded.source_id}:retry-parse",
        headers=headers,
        json=request,
    )
    second = client.post(
        f"/v1/sources/{uploaded.source_id}:retry-parse",
        headers=headers,
        json=request,
    )
    assert first.status_code == second.status_code == 202
    assert second.headers["Idempotency-Replayed"] == "true"
    with factory() as session:  # type: ignore[operator]
        tasks = session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_id == uploaded.source_id)
        )
        assert tasks == 2


@pytest.mark.parametrize(
    "fixture",
    (
        ROOT / "tests/security-fixtures/magic-mismatch.pdf",
        ROOT / "tests/security-fixtures/ratio.docx",
        ROOT / "tests/security-fixtures/traversal.docx",
        ROOT / "tests/security-fixtures/encrypted.pdf",
        ROOT / "tests/security-fixtures/corrupt.pdf",
        ROOT / "tests/security-fixtures/active.html",
    ),
    ids=lambda value: value.name,
)
def test_malicious_or_invalid_sources_never_reach_clean_or_parse(
    runtime: dict[str, object], fixture: Path
) -> None:
    uploaded = _upload(
        runtime,
        subject=f"threat-{fixture.stem}",
        filename=fixture.name,
        content=fixture.read_bytes(),
    )
    assert uploaded.complete_status == 202
    factory = runtime["factory"]
    with factory() as session:  # type: ignore[operator]
        source = session.get(Source, uploaded.source_id)
        assert source is not None
        organization_id = source.organization_id
    assert process_source_pipeline(
        factory,  # type: ignore[arg-type]
        uploaded.source_id,
        organization_id,
        object_store=runtime["worker_store"],  # type: ignore[arg-type]
        clamav=runtime["clamav"],  # type: ignore[arg-type]
    ) == "rejected"
    with factory() as session:  # type: ignore[operator]
        source = session.get(Source, uploaded.source_id)
        artifact_count = session.scalar(
            select(func.count())
            .select_from(SourceArtifact)
            .where(SourceArtifact.source_id == uploaded.source_id)
        )
        assert source is not None
        assert source.status == "rejected"
        assert source.scan_status == "rejected"
        assert source.parse_attempt == 0
        assert artifact_count == 0


def test_post_complete_tamper_and_cross_tenant_access_are_denied(
    runtime: dict[str, object]
) -> None:
    content = b"<html><body>original</body></html>"
    uploaded = _upload(
        runtime,
        subject="owner",
        filename="private.html",
        content=content,
    )
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    assert client.get(
        f"/v1/sources/{uploaded.source_id}", headers=_headers("foreign")
    ).status_code == 404
    assert client.post(
        f"/v1/upload-sessions/{uploaded.session_id}:complete",
        headers={**_headers("foreign"), "Idempotency-Key": "foreign-complete"},
        json={"schemaVersion": 1, "data": {}, "baseRevisionId": None},
    ).status_code == 404
    api_store: MinioPrivateObjectStore = runtime["api_store"]  # type: ignore[assignment]
    tampered = b"<html><body>tampered</body></html>"
    api_store._client.put_object(  # noqa: SLF001
        BUCKET,
        uploaded.object_key,
        data=__import__("io").BytesIO(tampered),
        length=len(tampered),
        content_type="text/html",
    )
    factory = runtime["factory"]
    with factory() as session:  # type: ignore[operator]
        source = session.get(Source, uploaded.source_id)
        assert source is not None
        organization_id = source.organization_id
    assert process_source_pipeline(
        factory,  # type: ignore[arg-type]
        uploaded.source_id,
        organization_id,
        object_store=runtime["worker_store"],  # type: ignore[arg-type]
        clamav=runtime["clamav"],  # type: ignore[arg-type]
    ) == "rejected"
    with factory() as session:  # type: ignore[operator]
        source = session.get(Source, uploaded.source_id)
        assert source is not None and source.error_code == "SOURCE_BYTES_CHANGED"


def test_create_complete_retries_and_api_restart_recover_same_source(
    runtime: dict[str, object]
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    content = b"<html><body>retry</body></html>"
    digest = hashlib.sha256(content).hexdigest()
    payload = {
        "schemaVersion": 1,
        "data": {
            "filename": "retry.html",
            "declaredMimeType": "text/html",
            "expectedSha256": digest,
            "sizeBytes": len(content),
        },
        "baseRevisionId": None,
    }
    headers = {**_headers("network-retry"), "Idempotency-Key": "stable-create"}
    first = client.post("/v1/upload-sessions", headers=headers, json=payload)
    second = client.post("/v1/upload-sessions", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["resourceId"] == second.json()["resourceId"]
    assert first.json()["data"]["sourceId"] == second.json()["data"]["sourceId"]
    data = second.json()["data"]
    assert httpx.post(
        data["uploadUrl"],
        data=data["formFields"],
        files={"file": ("retry.html", content, "text/html")},
    ).status_code in {200, 204}
    complete_headers = {
        **_headers("network-retry"),
        "Idempotency-Key": "stable-complete",
    }
    mutation = {"schemaVersion": 1, "data": {}, "baseRevisionId": None}
    complete_first = client.post(
        f"/v1/upload-sessions/{data['uploadSessionId']}:complete",
        headers=complete_headers,
        json=mutation,
    )
    complete_second = client.post(
        f"/v1/upload-sessions/{data['uploadSessionId']}:complete",
        headers=complete_headers,
        json=mutation,
    )
    assert complete_first.status_code == complete_second.status_code == 202
    assert complete_second.headers["Idempotency-Replayed"] == "true"
    closed = client.post("/v1/upload-sessions", headers=headers, json=payload)
    assert closed.status_code == 409
    assert closed.json()["code"] == "upload_session_closed"
    factory = runtime["factory"]
    with factory() as session:  # type: ignore[operator]
        tasks = session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_id == data["sourceId"])
        )
        assert tasks == 1
    restarted = create_app(
        settings=runtime["settings"],  # type: ignore[arg-type]
        session_factory=factory,  # type: ignore[arg-type]
        object_store=runtime["api_store"],
    )
    with TestClient(restarted) as restarted_client:
        recovered = restarted_client.get(
            f"/v1/sources/{data['sourceId']}", headers=_headers("network-retry")
        )
    assert recovered.status_code == 200
    assert recovered.json()["data"]["status"] == "uploaded"
