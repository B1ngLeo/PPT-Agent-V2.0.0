"""Fail-closed quarantine scanner and clean-only source parser pipeline."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import socket
import struct
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from instant_ppt_domain.artifacts import tenant_object_key
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import Artifact, SourceArtifact
from instant_ppt_domain.reconciliation import StoredObject
from instant_ppt_domain.sources import SourceNotFound, get_source
from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error
from sqlalchemy.orm import Session, sessionmaker
from urllib3.exceptions import HTTPError

from instant_ppt_worker.models import SecurityDecision, SecurityFinding
from instant_ppt_worker.security import inspect_source
from instant_ppt_worker.settings import WorkerContract
from instant_ppt_worker.source_parser import parse_source

CHUNK_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 25 * 1024 * 1024
SOURCE_RETENTION_DAYS = 30


class ScannerUnavailable(RuntimeError):
    pass


class SourceObjectError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerObjectSettings:
    endpoint: str
    region: str
    access_key: str
    secret_key: str = field(repr=False)
    bucket: str

    @classmethod
    def from_env(cls) -> WorkerObjectSettings:
        return cls(
            endpoint=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
            region=os.getenv("S3_REGION", "us-east-1"),
            access_key=os.getenv("S3_ACCESS_KEY", "instant-ppt-local"),
            secret_key=os.getenv("S3_SECRET_KEY", "local-development-only"),
            bucket=os.getenv("S3_BUCKET", "instant-ppt-private"),
        )


@dataclass(frozen=True, slots=True)
class ClamAvSettings:
    host: str = "localhost"
    port: int = 3310
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> ClamAvSettings:
        return cls(
            host=os.getenv("CLAMAV_HOST", "localhost"),
            port=int(os.getenv("CLAMAV_PORT", "3310")),
            timeout_seconds=float(os.getenv("CLAMAV_TIMEOUT_SECONDS", "15")),
        )


@dataclass(frozen=True, slots=True)
class PublishedSourceArtifact:
    artifact_id: str
    kind: str
    object_key: str
    sha256: str
    media_type: str
    size_bytes: int
    parser_version: str


class WorkerObjectStore:
    def __init__(self, settings: WorkerObjectSettings) -> None:
        parsed = urlsplit(
            settings.endpoint
            if "://" in settings.endpoint
            else f"http://{settings.endpoint}"
        )
        if not parsed.netloc or parsed.path not in {"", "/"}:
            raise ValueError("S3 endpoint must contain only scheme, host, and port")
        self.bucket = settings.bucket
        self.client = Minio(
            parsed.netloc,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=parsed.scheme == "https",
            region=settings.region,
        )

    def download(self, object_key: str, target: Path, *, max_bytes: int) -> str:
        response = None
        digest = hashlib.sha256()
        size = 0
        try:
            response = self.client.get_object(self.bucket, object_key)
            with target.open("xb") as stream:
                for chunk in response.stream(CHUNK_BYTES):
                    size += len(chunk)
                    if size > max_bytes:
                        raise SourceObjectError("source exceeds the download limit")
                    digest.update(chunk)
                    stream.write(chunk)
        except SourceObjectError:
            raise
        except (S3Error, HTTPError, OSError) as error:
            raise SourceObjectError("source object could not be downloaded") from error
        finally:
            if response is not None:
                response.close()
                response.release_conn()
        return digest.hexdigest()

    def promote(self, source_key: str, clean_key: str) -> None:
        try:
            self.client.copy_object(
                self.bucket, clean_key, CopySource(self.bucket, source_key)
            )
            self.client.remove_object(self.bucket, source_key)
        except (S3Error, HTTPError) as error:
            raise SourceObjectError("source object could not be promoted") from error

    def put_file(self, object_key: str, path: Path, media_type: str) -> None:
        try:
            self.client.fput_object(
                self.bucket,
                object_key,
                str(path),
                content_type=media_type,
                metadata={"sha256": _sha256_file(path)},
            )
        except (S3Error, HTTPError, OSError) as error:
            raise SourceObjectError("parsed artifact could not be published") from error

    def remove(self, object_key: str) -> None:
        try:
            self.client.remove_object(self.bucket, object_key)
        except (S3Error, HTTPError) as error:
            raise SourceObjectError("artifact object could not be removed") from error

    def list_objects(self, prefix: str) -> list[StoredObject]:
        try:
            return [
                StoredObject(item.object_name, item.last_modified)
                for item in self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
                if item.object_name and item.last_modified
            ]
        except (S3Error, HTTPError) as error:
            raise SourceObjectError("artifact objects could not be listed") from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clamav_scan(path: Path, settings: ClamAvSettings) -> str | None:
    """Return a malware signature, or None when clamd reports OK."""
    try:
        with socket.create_connection(
            (settings.host, settings.port), timeout=settings.timeout_seconds
        ) as connection:
            connection.settimeout(settings.timeout_seconds)
            connection.sendall(b"zINSTREAM\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
                    connection.sendall(struct.pack(">I", len(chunk)))
                    connection.sendall(chunk)
            connection.sendall(struct.pack(">I", 0))
            response = bytearray()
            while len(response) < 4096:
                block = connection.recv(1024)
                if not block:
                    break
                response.extend(block)
                if b"\0" in block or b"\n" in block:
                    break
    except (OSError, TimeoutError) as error:
        raise ScannerUnavailable("ClamAV is unavailable") from error
    message = bytes(response).rstrip(b"\0\r\n").decode("utf-8", errors="replace")
    if message.endswith(" OK"):
        return None
    if message.endswith(" FOUND"):
        signature = message.rsplit(": ", 1)[-1].removesuffix(" FOUND").strip()
        return signature or "unknown"
    raise ScannerUnavailable(f"ClamAV returned an unusable response: {message[:200]}")


def _mark_failure(
    factory: sessionmaker[Session],
    source_id: str,
    organization_id: str,
    *,
    stage: str,
    code: str,
    detail: str,
    retryable: bool,
    decision: SecurityDecision | None = None,
) -> None:
    with factory.begin() as session:
        source = get_source(session, source_id, organization_id, for_update=True)
        if source.status == "parsed":
            return
        source.status = "rejected" if stage == "scan" else "parse_failed"
        if stage == "scan":
            source.scan_status = "failed" if retryable else "rejected"
            source.scan_completed_at = datetime.now(UTC)
            if decision is not None:
                source.scan_decision = decision.model_dump(by_alias=True, mode="json")
                source.detected_mime_type = decision.detected_type
        else:
            source.parse_status = "failed"
            source.parse_completed_at = datetime.now(UTC)
        source.error_code = code
        source.error_detail = detail[:1000]
        source.retryable = retryable
        source.lock_version += 1


def _claim_source(
    factory: sessionmaker[Session], source_id: str, organization_id: str
) -> tuple[str, str, str, datetime, bool, dict[str, Any]] | None:
    with factory.begin() as session:
        source = get_source(session, source_id, organization_id, for_update=True)
        if source.status == "parsed" or (
            source.status == "rejected" and not source.retryable
        ):
            return None
        if source.status in {"scanning", "parsing"}:
            return None
        artifact = session.get(Artifact, source.input_artifact_id)
        if (
            artifact is None
            or artifact.organization_id != organization_id
            or artifact.sha256 != source.source_sha256
        ):
            raise SourceNotFound("source input artifact violates the tenant boundary")
        scan_required = source.scan_status != "clean"
        if scan_required:
            if source.scan_attempt >= 5:
                source.retryable = False
                return None
            source.status = "scanning"
            source.scan_status = "running"
            source.scan_attempt += 1
        else:
            if source.parse_attempt >= 5:
                source.retryable = False
                return None
            source.status = "parsing"
            source.parse_status = "running"
            source.parse_attempt += 1
        source.error_code = None
        source.error_detail = None
        source.retryable = False
        source.lock_version += 1
        return (
            artifact.object_key,
            source.extension,
            source.source_sha256,
            source.created_at,
            scan_required,
            dict(source.scan_decision),
        )


def _set_clean(
    factory: sessionmaker[Session],
    source_id: str,
    organization_id: str,
    decision: SecurityDecision,
    clean_key: str,
) -> None:
    with factory.begin() as session:
        source = get_source(session, source_id, organization_id, for_update=True)
        artifact = session.get(Artifact, source.input_artifact_id)
        if artifact is None or artifact.organization_id != organization_id:
            raise SourceNotFound("source input artifact is unavailable")
        artifact.partition = "clean"
        artifact.object_key = clean_key
        source.status = "clean"
        source.scan_status = "clean"
        source.detected_mime_type = decision.detected_type
        source.scan_decision = decision.model_dump(by_alias=True, mode="json")
        source.scan_completed_at = datetime.now(UTC)
        source.error_code = None
        source.error_detail = None
        source.retryable = False
        source.lock_version += 1


def _publish_parse_result(
    factory: sessionmaker[Session],
    store: WorkerObjectStore,
    source_id: str,
    organization_id: str,
    result: dict[str, object],
) -> None:
    parser_version = WorkerContract().parser_version
    paths = [Path(value) for value in result["paths"]]  # type: ignore[arg-type]
    markdown_path = next(path for path in paths if path.name == "source.md")
    profile_path = next(
        path for path in paths if path.name == "conversion-profile.json"
    )
    asset_paths = [
        path
        for path in paths
        if path.name not in {"source.md", "conversion-profile.json", "source-package.json"}
    ]
    pending: list[tuple[PublishedSourceArtifact, Path]] = []
    for kind, path, media_type in (
        ("markdown", markdown_path, "text/markdown"),
        ("conversion_profile", profile_path, "application/json"),
    ):
        artifact_id = new_ulid()
        pending.append(
            (
                PublishedSourceArtifact(
                    artifact_id=artifact_id,
                    kind=kind,
                    object_key=tenant_object_key(
                        organization_id, "published", artifact_id
                    ),
                    sha256=_sha256_file(path),
                    media_type=media_type,
                    size_bytes=path.stat().st_size,
                    parser_version=parser_version,
                ),
                path,
            )
        )
    for path in asset_paths:
        artifact_id = new_ulid()
        pending.append(
            (
                PublishedSourceArtifact(
                    artifact_id=artifact_id,
                    kind="asset",
                    object_key=tenant_object_key(
                        organization_id, "published", artifact_id
                    ),
                    sha256=_sha256_file(path),
                    media_type=mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                    size_bytes=path.stat().st_size,
                    parser_version=parser_version,
                ),
                path,
            )
        )
    for item, path in pending:
        store.put_file(item.object_key, path, item.media_type)

    markdown_id = next(item.artifact_id for item, _ in pending if item.kind == "markdown")
    profile_id = next(
        item.artifact_id for item, _ in pending if item.kind == "conversion_profile"
    )
    asset_ids = [item.artifact_id for item, _ in pending if item.kind == "asset"]
    package = dict(result["sourcePackage"])  # type: ignore[arg-type]
    package.update(
        {
            "markdownArtifactId": markdown_id,
            "conversionProfileArtifactId": profile_id,
            "assetArtifactIds": asset_ids,
            "parserVersion": parser_version,
        }
    )
    now = datetime.now(UTC)
    with factory.begin() as session:
        source = get_source(session, source_id, organization_id, for_update=True)
        if source.status == "parsed":
            return
        for item, _ in pending:
            artifact = Artifact(
                id=item.artifact_id,
                organization_id=organization_id,
                artifact_type=f"source_{item.kind}",
                partition="published",
                object_key=item.object_key,
                sha256=item.sha256,
                media_type=item.media_type,
                size_bytes=item.size_bytes,
                status="published",
                retention_expires_at=now + timedelta(days=SOURCE_RETENTION_DAYS),
            )
            session.add(artifact)
            session.add(
                SourceArtifact(
                    id=new_ulid(),
                    organization_id=organization_id,
                    source_id=source_id,
                    artifact_id=item.artifact_id,
                    kind=item.kind,
                    parser_version=item.parser_version,
                )
            )
        source.status = "parsed"
        source.parse_status = "succeeded"
        source.source_package = package
        source.parser_version = parser_version
        source.parse_completed_at = now
        source.error_code = None
        source.error_detail = None
        source.retryable = False
        source.lock_version += 1


def process_source_pipeline(
    factory: sessionmaker[Session],
    source_id: str,
    organization_id: str,
    *,
    object_store: WorkerObjectStore | None = None,
    clamav: ClamAvSettings | None = None,
) -> str:
    """Process one source idempotently, persisting every recoverable boundary."""
    claimed = _claim_source(factory, source_id, organization_id)
    if claimed is None:
        return "noop"
    (
        object_key,
        extension,
        expected_sha256,
        created_at,
        scan_required,
        stored_decision,
    ) = claimed
    store = object_store or WorkerObjectStore(WorkerObjectSettings.from_env())
    clamav_settings = clamav or ClamAvSettings.from_env()
    with tempfile.TemporaryDirectory(prefix="instant-ppt-source-") as directory:
        workspace = Path(directory)
        source_path = workspace / f"source{extension}"
        try:
            actual_sha256 = store.download(
                object_key, source_path, max_bytes=MAX_SOURCE_BYTES
            )
            if actual_sha256 != expected_sha256:
                _mark_failure(
                    factory,
                    source_id,
                    organization_id,
                    stage="scan",
                    code="SOURCE_BYTES_CHANGED",
                    detail="隔离区对象与完成上传时的校验值不一致",
                    retryable=False,
                )
                return "rejected"
            if scan_required:
                malware = clamav_scan(source_path, clamav_settings)
                inspection = inspect_source(source_path)
                findings = list(inspection.findings)
                if malware:
                    findings.append(
                        SecurityFinding(
                            code="SOURCE_MALWARE_DETECTED",
                            message=f"ClamAV detected {malware}",
                        )
                    )
                decision = SecurityDecision(
                    decision="rejected" if findings else "clean",
                    source_key=object_key,
                    source_sha256=actual_sha256,
                    detected_type=inspection.detected_type,
                    scanner="clamav@1.4.3+intake@1",
                    findings=findings,
                    checked_at=datetime.now(UTC).isoformat().replace(
                        "+00:00", "Z"
                    ),
                )
                if findings:
                    _mark_failure(
                        factory,
                        source_id,
                        organization_id,
                        stage="scan",
                        code=findings[0].code,
                        detail=findings[0].message,
                        retryable=False,
                        decision=decision,
                    )
                    return "rejected"
                clean_key = tenant_object_key(
                    organization_id, "clean", PureArtifactId.from_key(object_key)
                )
                store.promote(object_key, clean_key)
                decision = decision.model_copy(update={"source_key": clean_key})
                _set_clean(factory, source_id, organization_id, decision, clean_key)
            else:
                clean_key = object_key
                decision = SecurityDecision.model_validate(stored_decision)
                if (
                    decision.decision != "clean"
                    or decision.source_key != clean_key
                    or decision.source_sha256 != actual_sha256
                ):
                    raise SourceObjectError("persisted clean decision is not bound to source")
        except ScannerUnavailable:
            _mark_failure(
                factory,
                source_id,
                organization_id,
                stage="scan",
                code="SOURCE_SCANNER_UNAVAILABLE",
                detail="安全扫描服务暂不可用",
                retryable=True,
            )
            raise
        except SourceObjectError:
            _mark_failure(
                factory,
                source_id,
                organization_id,
                stage="scan",
                code="SOURCE_OBJECT_UNAVAILABLE",
                detail="隔离区对象暂不可用",
                retryable=True,
            )
            raise

        if scan_required:
            with factory.begin() as session:
                source = get_source(session, source_id, organization_id, for_update=True)
                if source.parse_attempt >= 5:
                    source.retryable = False
                    return "parse_attempt_limit"
                source.status = "parsing"
                source.parse_status = "running"
                source.parse_attempt += 1
                source.lock_version += 1
        decision_path = workspace / "decision.json"
        decision_path.write_text(
            decision.model_dump_json(by_alias=True), encoding="utf-8"
        )
        output_dir = workspace / "parsed"
        try:
            result = parse_source(
                clean_key,
                source_path,
                decision_path,
                output_dir,
                source_id=source_id,
                organization_id=organization_id,
                created_at=created_at.astimezone(UTC).isoformat().replace(
                    "+00:00", "Z"
                ),
            )
            _publish_parse_result(
                factory, store, source_id, organization_id, result
            )
            return "parsed"
        except Exception as error:
            _mark_failure(
                factory,
                source_id,
                organization_id,
                stage="parse",
                code="SOURCE_PARSE_FAILED",
                detail=str(error),
                retryable=True,
            )
            raise


class PureArtifactId:
    @staticmethod
    def from_key(object_key: str) -> str:
        artifact_id = object_key.rsplit("/", 1)[-1]
        if len(artifact_id) != 26:
            raise SourceObjectError("source object key is invalid")
        return artifact_id
