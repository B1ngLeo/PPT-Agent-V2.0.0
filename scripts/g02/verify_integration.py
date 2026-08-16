"""Stable G02 PostgreSQL/Redis/Celery integration and evidence runner."""

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

import psycopg
from instant_ppt_domain.migrations import upgrade
from redis import Redis

ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE = "instant_ppt_g02_test"
TEST_DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@localhost:5432/"
    f"{TEST_DATABASE}"
)
ADMIN_DATABASE_URL = (
    "postgresql://instant_ppt:local-development-only@localhost:5432/postgres"
)
EVENTS_URL = "redis://localhost:6379/14"
BROKER_URL = "redis://localhost:6379/15"


def _run(command: list[str], *, environment: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def _wait_for_postgres() -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(ADMIN_DATABASE_URL, connect_timeout=2):
                return
        except psycopg.OperationalError:
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready within 90 seconds")


def _ensure_test_database() -> None:
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DATABASE,)
        ).fetchone()
        if exists is None:
            connection.execute(f'CREATE DATABASE "{TEST_DATABASE}"')


def _wait_for_redis() -> None:
    client = Redis.from_url(EVENTS_URL)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if client.ping():
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Redis did not become ready within 60 seconds")


def _write_evidence(junit_path: Path, started_at: datetime, completed_at: datetime) -> None:
    tree = ET.parse(junit_path)
    cases = []
    for case in tree.findall(".//testcase"):
        name = case.attrib.get("name", "unknown")
        status = "passed"
        if case.find("failure") is not None:
            status = "failed"
        elif case.find("error") is not None:
            status = "error"
        elif case.find("skipped") is not None:
            status = "skipped"
        cases.append(
            {
                "name": name,
                "className": case.attrib.get("classname", ""),
                "status": status,
                "durationSeconds": float(case.attrib.get("time", "0")),
            }
        )
    evidence = {
        "schemaVersion": 1,
        "goal": "G02",
        "startedAt": started_at.isoformat().replace("+00:00", "Z"),
        "completedAt": completed_at.isoformat().replace("+00:00", "Z"),
        "database": "PostgreSQL 17.6 isolated test database",
        "redis": "Redis 7.4.2 isolated DB 14/15",
        "requiredConsecutiveIterations": 10,
        "command": "pnpm verify:integration",
        "status": "passed",
        "summary": {
            "total": len(cases),
            "passed": sum(case["status"] == "passed" for case in cases),
            "failed": sum(case["status"] in {"failed", "error"} for case in cases),
            "skipped": sum(case["status"] == "skipped" for case in cases),
        },
        "cases": cases,
        "junitSha256": hashlib.sha256(junit_path.read_bytes()).hexdigest(),
    }
    target = ROOT / "docs" / "evidence" / "recovery" / "g02-recovery-results.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    _run(["docker", "compose", "up", "-d", "postgres", "redis"])
    _wait_for_postgres()
    _wait_for_redis()
    _ensure_test_database()
    upgrade(TEST_DATABASE_URL)
    Redis.from_url(EVENTS_URL).flushdb()
    Redis.from_url(BROKER_URL).flushdb()

    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": TEST_DATABASE_URL,
            "G02_TEST_DATABASE_URL": TEST_DATABASE_URL,
            "REDIS_EVENTS_URL": EVENTS_URL,
            "G02_TEST_REDIS_EVENTS_URL": EVENTS_URL,
            "CELERY_BROKER_URL": BROKER_URL,
            "G02_TEST_CELERY_BROKER_URL": BROKER_URL,
            "CELERY_VISIBILITY_TIMEOUT_SECONDS": "3",
            "G02_RUN_CELERY_KILL": "1",
        }
    )
    junit_path = ROOT / ".tmp" / "g02-integration-junit.xml"
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/g02",
            "--basetemp",
            ".tmp/pytest-g02-integration",
            f"--junitxml={junit_path}",
        ],
        environment=environment,
    )
    completed_at = datetime.now(UTC)
    _write_evidence(junit_path, started_at, completed_at)
    print("G02 integration and 10-iteration recovery matrix passed")


if __name__ == "__main__":
    main()
