from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from instant_ppt_domain.migrations import upgrade
from minio import Minio
from minio.error import S3Error

ROOT = Path(__file__).resolve().parents[2]
ADMIN_DATABASE_URL = (
    "postgresql://instant_ppt:local-development-only@127.0.0.1:5432/postgres"
)
TEST_DATABASE = "instant_ppt_g08_test"
TEST_DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@127.0.0.1:5432/"
    f"{TEST_DATABASE}"
)


def _wait_for_postgres() -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(ADMIN_DATABASE_URL, connect_timeout=2):
                return
        except psycopg.OperationalError:
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready within 90 seconds")


def _recreate_database() -> None:
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{TEST_DATABASE}"')
    upgrade(TEST_DATABASE_URL)


def _write_governance_evidence(junit_path: Path) -> None:
    tree = ET.parse(junit_path)
    cases = tree.findall(".//testcase")
    client = Minio(
        "localhost:9000",
        access_key="instant-ppt-local",
        secret_key="local-development-only",
        secure=False,
        region="us-east-1",
    )
    encryption = client.get_bucket_encryption("instant-ppt-private")
    lifecycle = client.get_bucket_lifecycle("instant-ppt-private")
    try:
        public_policy = client.get_bucket_policy("instant-ppt-private")
    except S3Error as error:
        if error.code != "NoSuchBucketPolicy":
            raise
        public_policy = None
    matching = [
        rule
        for rule in lifecycle.rules
        if rule.rule_id == "instant-ppt-expired-delete-markers"
    ]
    runtime_environment = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
            "instant-ppt-minio-1",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    evidence = {
        "schemaVersion": 1,
        "goal": "G08",
        "generatedAt": datetime.now(UTC).isoformat(),
        "result": "passed",
        "testDatabase": TEST_DATABASE,
        "junit": {
            "path": "docs/evidence/g08-integration-junit.xml",
            "tests": len(cases),
            "failures": sum(
                case.find("failure") is not None or case.find("error") is not None
                for case in cases
            ),
            "skipped": sum(case.find("skipped") is not None for case in cases),
        },
        "bucket": {
            "name": "instant-ppt-private",
            "publicPolicy": public_policy is not None,
            "defaultEncryption": encryption.rule.sse_algorithm,
            "lifecycleRule": matching[0].rule_id,
            "lifecyclePrefix": matching[0].rule_filter.prefix,
            "expiredDeleteMarkerCleanup": (
                matching[0].expiration.expired_object_delete_marker
            ),
            "staleMultipartExpiry": next(
                value.split("=", 1)[1]
                for value in runtime_environment
                if value.startswith("MINIO_API_STALE_UPLOADS_EXPIRY=")
            ),
            "staleMultipartCleanupInterval": next(
                value.split("=", 1)[1]
                for value in runtime_environment
                if value.startswith("MINIO_API_STALE_UPLOADS_CLEANUP_INTERVAL=")
            ),
        },
        "retentionAuthority": (
            "PostgreSQL retention_expires_at plus tenant-scoped reconciliation"
        ),
        "productionRequirement": (
            "Replace the local static KMS key with approved MinIO KES/KMS configuration."
        ),
    }
    target = ROOT / "docs" / "evidence" / "security" / "g08-object-governance.json"
    target.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    subprocess.run(
        ["docker", "compose", "up", "-d", "postgres", "minio"],
        cwd=ROOT,
        check=True,
    )
    _wait_for_postgres()
    _recreate_database()
    environment = os.environ.copy()
    environment.update(
        {
            "G08_TEST_DATABASE_URL": TEST_DATABASE_URL,
            "G08_RUN_MINIO": "1",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_PUBLIC_ENDPOINT": "http://localhost:9000",
            "S3_REGION": "us-east-1",
            "S3_ACCESS_KEY": "instant-ppt-local",
            "S3_SECRET_KEY": "local-development-only",
            "S3_BUCKET": "instant-ppt-private",
        }
    )
    junit_path = ROOT / "docs" / "evidence" / "g08-integration-junit.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/g08",
            "-q",
            "--basetemp",
            ".tmp/pytest-g08-integration",
            f"--junitxml={junit_path}",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    if result.returncode == 0:
        _write_governance_evidence(junit_path)
        print("G08 isolated reconciliation and MinIO governance matrix passed")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
