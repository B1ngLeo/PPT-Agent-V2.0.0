"""G03 identity, tenancy, migration, and private-object evidence runner."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import psycopg
from alembic import command
from instant_ppt_domain.migrations import (
    alembic_config,
    downgrade,
    upgrade,
)
from redis import Redis

ROOT = Path(__file__).resolve().parents[2]
ADMIN_DATABASE_URL = (
    "postgresql://instant_ppt:local-development-only@localhost:5432/postgres"
)
TEST_DATABASE = "instant_ppt_g03_test"
MIGRATION_DATABASE = "instant_ppt_g03_migration_test"
TEST_DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@localhost:5432/"
    f"{TEST_DATABASE}"
)
MIGRATION_DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@localhost:5432/"
    f"{MIGRATION_DATABASE}"
)
MIGRATION_PSYCOPG_URL = (
    "postgresql://instant_ppt:local-development-only@localhost:5432/"
    f"{MIGRATION_DATABASE}"
)
EVENTS_URL = "redis://localhost:6379/12"
BROKER_URL = "redis://localhost:6379/13"
SYNTHETIC_ORGANIZATION_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAA"
SERVICE_ACTOR_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAB"
SNAPSHOT_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAX"
JOB_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAY"


def _run(command_line: list[str], *, environment: dict[str, str] | None = None) -> None:
    subprocess.run(command_line, cwd=ROOT, env=environment, check=True)


def _wait_for_postgres() -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(ADMIN_DATABASE_URL, connect_timeout=2):
                return
        except psycopg.OperationalError:
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready within 90 seconds")


def _wait_for_redis() -> None:
    client = Redis.from_url(EVENTS_URL)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if client.ping():
                return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise RuntimeError("Redis did not become ready within 60 seconds")


def _wait_for_minio() -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with urlopen(  # noqa: S310
                "http://localhost:9000/minio/health/live", timeout=2
            ) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(1)
    raise RuntimeError("MinIO did not become ready within 90 seconds")


def _ensure_database(name: str, *, recreate: bool = False) -> None:
    if name not in {TEST_DATABASE, MIGRATION_DATABASE}:
        raise ValueError("refusing to manage an unexpected database")
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if exists is not None and recreate:
            connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
            exists = None
        if exists is None:
            connection.execute(f'CREATE DATABASE "{name}"')


def _insert_g02_fixture() -> tuple[object, ...]:
    with psycopg.connect(MIGRATION_PSYCOPG_URL) as connection:
        connection.execute(
            """
            INSERT INTO organizations (id, kind, name)
            VALUES (%s, 'synthetic', 'G02 preservation fixture')
            """,
            (SYNTHETIC_ORGANIZATION_ID,),
        )
        connection.execute(
            """
            INSERT INTO service_actors (id, organization_id, name)
            VALUES (%s, %s, 'G02 fixture actor')
            """,
            (SERVICE_ACTOR_ID, SYNTHETIC_ORGANIZATION_ID),
        )
        connection.execute(
            """
            INSERT INTO generation_snapshots (
                id, organization_id, draft_id, intent_revision_id,
                outline_revision_id, template_version_id, mode_id,
                source_hashes, prompt_version, engine_version,
                container_version, font_pack_version, provider_config_version,
                snapshot_sha256, payload
            ) VALUES (
                %s, %s, %s, %s, %s, %s, 'native', '[]'::jsonb,
                'g02-preserved', 'g02-preserved', 'g02-preserved',
                'g02-preserved', 'g02-preserved', %s, %s::jsonb
            )
            """,
            (
                SNAPSHOT_ID,
                SYNTHETIC_ORGANIZATION_ID,
                "01ARZ3NDEKTSV4RRFFQ69G5FA1",
                "01ARZ3NDEKTSV4RRFFQ69G5FA2",
                "01ARZ3NDEKTSV4RRFFQ69G5FA3",
                "01ARZ3NDEKTSV4RRFFQ69G5FA4",
                "b" * 64,
                json.dumps({"preserved": True}),
            ),
        )
        connection.execute(
            """
            INSERT INTO generation_jobs (
                id, organization_id, snapshot_id, status, stage, latest_seq,
                attempt, lock_version, progress_completed, progress_total,
                test_behavior
            ) VALUES (
                %s, %s, %s, 'running', 'slide_generation', 7,
                2, 3, 1, 3, %s::jsonb
            )
            """,
            (
                JOB_ID,
                SYNTHETIC_ORGANIZATION_ID,
                SNAPSHOT_ID,
                json.dumps({"migrationCanary": "g02-data"}),
            ),
        )
        connection.commit()
        return _job_fingerprint(connection)


def _job_fingerprint(connection: psycopg.Connection[tuple[object, ...]]) -> tuple[object, ...]:
    row = connection.execute(
        """
        SELECT id, organization_id, snapshot_id, status, stage, latest_seq,
               attempt, lock_version, progress_completed, progress_total,
               test_behavior
        FROM generation_jobs WHERE id = %s
        """,
        (JOB_ID,),
    ).fetchone()
    if row is None:
        raise AssertionError("G02 preservation fixture disappeared")
    return tuple(row)


def _assert_g03_identity_seed(expected_job: tuple[object, ...]) -> None:
    with psycopg.connect(MIGRATION_PSYCOPG_URL) as connection:
        assert _job_fingerprint(connection) == expected_job
        organization = connection.execute(
            """
            SELECT kind, personal_owner_user_id, slug
            FROM organizations WHERE id = %s
            """,
            (SYNTHETIC_ORGANIZATION_ID,),
        ).fetchone()
        assert organization is not None
        assert organization[0] == "personal"
        assert organization[1] is not None
        assert str(organization[2]).startswith("personal-")
        for table in ("users", "memberships", "entitlements"):
            count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
            assert count == (1,)


def _verify_migration_preservation() -> dict[str, object]:
    _ensure_database(MIGRATION_DATABASE, recreate=True)
    upgrade(MIGRATION_DATABASE_URL, "0001_g02")
    expected_job = _insert_g02_fixture()
    upgrade(MIGRATION_DATABASE_URL)
    _assert_g03_identity_seed(expected_job)
    command.check(alembic_config(MIGRATION_DATABASE_URL))
    downgrade(MIGRATION_DATABASE_URL, "0001_g02")
    with psycopg.connect(MIGRATION_PSYCOPG_URL) as connection:
        assert _job_fingerprint(connection) == expected_job
        organization_kind = connection.execute(
            "SELECT kind FROM organizations WHERE id = %s",
            (SYNTHETIC_ORGANIZATION_ID,),
        ).fetchone()
        assert organization_kind == ("synthetic",)
    upgrade(MIGRATION_DATABASE_URL)
    _assert_g03_identity_seed(expected_job)
    return {
        "status": "passed",
        "path": "0001_g02 -> head -> 0001_g02 -> head",
        "schemaDrift": "none",
        "preservedJobId": JOB_ID,
        "preservedFields": len(expected_job),
    }


def _write_evidence(
    junit_path: Path,
    started_at: datetime,
    completed_at: datetime,
    migration: dict[str, object],
) -> None:
    tree = ET.parse(junit_path)
    cases: list[dict[str, object]] = []
    for case in tree.findall(".//testcase"):
        status = "passed"
        if case.find("failure") is not None:
            status = "failed"
        elif case.find("error") is not None:
            status = "error"
        elif case.find("skipped") is not None:
            status = "skipped"
        cases.append(
            {
                "name": case.attrib.get("name", "unknown"),
                "className": case.attrib.get("classname", ""),
                "status": status,
                "durationSeconds": float(case.attrib.get("time", "0")),
            }
        )
    evidence = {
        "schemaVersion": 1,
        "goal": "G03",
        "startedAt": started_at.isoformat().replace("+00:00", "Z"),
        "completedAt": completed_at.isoformat().replace("+00:00", "Z"),
        "status": "passed",
        "environment": {
            "database": "PostgreSQL 17.6 isolated G03 databases",
            "redis": "Redis 7.4.2 isolated DB 12/13",
            "objectStore": "MinIO private bucket with real presigned HTTP requests",
        },
        "migrationPreservation": migration,
        "summary": {
            "total": len(cases),
            "passed": sum(case["status"] == "passed" for case in cases),
            "failed": sum(case["status"] in {"failed", "error"} for case in cases),
            "skipped": sum(case["status"] == "skipped" for case in cases),
        },
        "cases": cases,
        "junitSha256": hashlib.sha256(junit_path.read_bytes()).hexdigest(),
    }
    target = ROOT / "docs" / "evidence" / "security" / "g03-tenancy-results.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    _run(["docker", "compose", "up", "-d", "postgres", "redis", "minio"])
    _wait_for_postgres()
    _wait_for_redis()
    _wait_for_minio()
    migration = _verify_migration_preservation()
    _ensure_database(TEST_DATABASE)
    upgrade(TEST_DATABASE_URL)
    Redis.from_url(EVENTS_URL).flushdb()
    Redis.from_url(BROKER_URL).flushdb()

    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": TEST_DATABASE_URL,
            "G03_TEST_DATABASE_URL": TEST_DATABASE_URL,
            "REDIS_EVENTS_URL": EVENTS_URL,
            "G03_TEST_REDIS_EVENTS_URL": EVENTS_URL,
            "CELERY_BROKER_URL": BROKER_URL,
            "G03_TEST_CELERY_BROKER_URL": BROKER_URL,
            "APP_ENVIRONMENT": "test",
            "AUTH_MODE": "local",
            "DOWNLOAD_URL_TTL_SECONDS": "15",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_PUBLIC_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "instant-ppt-local",
            "S3_SECRET_KEY": "local-development-only",
            "S3_BUCKET": "instant-ppt-private",
            "G03_RUN_MINIO": "1",
        }
    )
    junit_path = ROOT / ".tmp" / "g03-integration-junit.xml"
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/g03",
            "--basetemp",
            ".tmp/pytest-g03-integration",
            f"--junitxml={junit_path}",
        ],
        environment=environment,
    )
    completed_at = datetime.now(UTC)
    _write_evidence(junit_path, started_at, completed_at, migration)
    print("G03 tenant isolation, migration, and private-object matrix passed")


if __name__ == "__main__":
    main()
