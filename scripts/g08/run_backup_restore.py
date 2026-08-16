from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from minio import Minio

ROOT = Path(__file__).resolve().parents[2]
POSTGRES_CONTAINER = "instant-ppt-postgres-1"
SOURCE_DATABASE = "instant_ppt"
RESTORE_DATABASE = "instant_ppt_g08_restore"
BACKUP_PATH = "/tmp/instant-ppt-g08.backup"
RESTORE_BUCKET = "instant-ppt-g08-restore"


def _docker(*arguments: str, capture: bool = True) -> str:
    completed = subprocess.run(
        ["docker", "exec", POSTGRES_CONTAINER, *arguments],
        cwd=ROOT,
        capture_output=capture,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def _database_counts(database: str) -> dict[str, int | str]:
    if database not in {SOURCE_DATABASE, RESTORE_DATABASE}:
        raise ValueError("unexpected database target")
    sql = """
    SELECT json_build_object(
      'alembicVersion', (SELECT version_num FROM alembic_version),
      'organizations', (SELECT count(*) FROM organizations),
      'drafts', (SELECT count(*) FROM drafts),
      'generationJobs', (SELECT count(*) FROM generation_jobs),
      'jobEvents', (SELECT count(*) FROM job_events),
      'artifacts', (SELECT count(*) FROM artifacts),
      'auditLogs', (SELECT count(*) FROM audit_logs),
      'reconciliationRuns', (SELECT count(*) FROM object_reconciliation_runs)
    );
    """
    return json.loads(_docker("psql", "-U", "instant_ppt", "-d", database, "-Atc", sql))


def _minio() -> tuple[Minio, str]:
    endpoint = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    parsed = urlsplit(endpoint if "://" in endpoint else f"http://{endpoint}")
    if not parsed.netloc or parsed.path not in {"", "/"}:
        raise ValueError("S3 endpoint must contain only scheme, host, and port")
    return (
        Minio(
            parsed.netloc,
            access_key=os.getenv("S3_ACCESS_KEY", "instant-ppt-local"),
            secret_key=os.getenv("S3_SECRET_KEY", "local-development-only"),
            secure=parsed.scheme == "https",
            region=os.getenv("S3_REGION", "us-east-1"),
        ),
        os.getenv("S3_BUCKET", "instant-ppt-private"),
    )


def _read_object(client: Minio, bucket: str, key: str) -> bytes:
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _object_restore() -> dict[str, object]:
    client, source_bucket = _minio()
    if RESTORE_BUCKET == source_bucket:
        raise ValueError("restore bucket must not equal source bucket")
    if not client.bucket_exists(source_bucket):
        raise RuntimeError("source object bucket is missing")
    canary_key: str | None = None
    source_objects = list(client.list_objects(source_bucket, recursive=True))
    if not source_objects:
        canary_key = "recovery/g08/backup-restore-canary.txt"
        payload = b"instant-ppt-g08-backup-restore"
        client.put_object(
            source_bucket,
            canary_key,
            io.BytesIO(payload),
            len(payload),
            content_type="text/plain",
        )
        source_objects = list(client.list_objects(source_bucket, recursive=True))

    if client.bucket_exists(RESTORE_BUCKET):
        for item in client.list_objects(RESTORE_BUCKET, recursive=True):
            client.remove_object(RESTORE_BUCKET, item.object_name)
        client.remove_bucket(RESTORE_BUCKET)
    client.make_bucket(RESTORE_BUCKET, location=os.getenv("S3_REGION", "us-east-1"))
    source_hashes: dict[str, str] = {}
    restored_hashes: dict[str, str] = {}
    try:
        for item in source_objects:
            payload = _read_object(client, source_bucket, item.object_name)
            source_hashes[item.object_name] = hashlib.sha256(payload).hexdigest()
            stat = client.stat_object(source_bucket, item.object_name)
            client.put_object(
                RESTORE_BUCKET,
                item.object_name,
                io.BytesIO(payload),
                len(payload),
                content_type=stat.content_type or "application/octet-stream",
            )
        for item in client.list_objects(RESTORE_BUCKET, recursive=True):
            restored_hashes[item.object_name] = hashlib.sha256(
                _read_object(client, RESTORE_BUCKET, item.object_name)
            ).hexdigest()
        if source_hashes != restored_hashes:
            raise RuntimeError("restored object hashes differ from source")
        return {
            "sourceBucket": source_bucket,
            "restoreBucket": RESTORE_BUCKET,
            "objectCount": len(source_hashes),
            "hashesMatched": True,
            "canaryUsedForEmptySource": canary_key is not None,
        }
    finally:
        for item in client.list_objects(RESTORE_BUCKET, recursive=True):
            client.remove_object(RESTORE_BUCKET, item.object_name)
        client.remove_bucket(RESTORE_BUCKET)
        if canary_key is not None:
            client.remove_object(source_bucket, canary_key)


def main() -> int:
    if not POSTGRES_CONTAINER.startswith("instant-ppt-postgres-"):
        raise SystemExit("unsafe postgres container target")
    source = _database_counts(SOURCE_DATABASE)
    try:
        _docker("pg_dump", "-U", "instant_ppt", "-d", SOURCE_DATABASE, "-Fc", "-f", BACKUP_PATH)
        backup_bytes = int(_docker("stat", "-c", "%s", BACKUP_PATH))
        _docker("dropdb", "-U", "instant_ppt", "--if-exists", RESTORE_DATABASE)
        _docker("createdb", "-U", "instant_ppt", RESTORE_DATABASE)
        _docker(
            "pg_restore",
            "-U",
            "instant_ppt",
            "-d",
            RESTORE_DATABASE,
            "--no-owner",
            "--no-privileges",
            BACKUP_PATH,
        )
        restored = _database_counts(RESTORE_DATABASE)
        if source != restored:
            raise RuntimeError("restored database counts or schema version differ")
        objects = _object_restore()
        report = {
            "schemaVersion": 1,
            "goal": "G08",
            "generatedAt": datetime.now(UTC).isoformat(),
            "result": "passed",
            "postgres": {
                "sourceDatabase": SOURCE_DATABASE,
                "restoreDatabase": RESTORE_DATABASE,
                "format": "pg_dump custom",
                "backupBytes": backup_bytes,
                "source": source,
                "restored": restored,
                "countsAndSchemaMatched": True,
            },
            "objects": objects,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        _docker("dropdb", "-U", "instant_ppt", "--if-exists", RESTORE_DATABASE)
        _docker("rm", "-f", BACKUP_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
