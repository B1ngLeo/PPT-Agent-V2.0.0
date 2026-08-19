"""Run the isolated G04 PostgreSQL, MinIO, scanner, and parser matrix."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from instant_ppt_domain.migrations import upgrade

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = "postgresql://instant_ppt:local-development-only@127.0.0.1:5432/postgres"
DATABASE = "instant_ppt_g04_test"
DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@127.0.0.1:5432/"
    f"{DATABASE}"
)
JUNIT = ROOT / "docs/evidence/security/g04-source-junit.xml"
EVIDENCE = ROOT / "docs/evidence/security/g04-source-results.json"


def main() -> None:
    deadline = time.monotonic() + 30
    while True:
        try:
            with psycopg.connect(ADMIN_URL, connect_timeout=2):
                break
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
    with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{DATABASE}"')
    upgrade(DATABASE_URL)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/g04/test_source_flow.py",
            "--basetemp",
            ".tmp/pytest-g04-integration",
            "--junitxml",
            str(JUNIT),
        ],
        cwd=ROOT,
        check=True,
    )
    suite = ET.parse(JUNIT).getroot()
    if suite.tag == "testsuites":
        suite = next(iter(suite))
    tests = [
        {
            "name": case.attrib["name"],
            "classname": case.attrib.get("classname", ""),
            "durationSeconds": float(case.attrib.get("time", "0")),
            "status": (
                "failed"
                if case.find("failure") is not None or case.find("error") is not None
                else "skipped"
                if case.find("skipped") is not None
                else "passed"
            ),
        }
        for case in suite.findall("testcase")
    ]
    evidence = {
        "schemaVersion": 1,
        "goal": "G04",
        "gate": "GATE-G04-SOURCE-SECURITY",
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "environment": {
            "database": "PostgreSQL 17.6",
            "objectStore": "MinIO RELEASE.2025-04-22",
            "scannerProtocol": "ClamAV clamd INSTREAM",
            "scannerFixture": "deterministic clamd protocol server",
            "parser": "source-parser@1+ppt-master-v4.7.0",
        },
        "formats": ["docx", "pdf", "pptx", "html"],
        "passed": sum(item["status"] == "passed" for item in tests),
        "failed": sum(item["status"] == "failed" for item in tests),
        "skipped": sum(item["status"] == "skipped" for item in tests),
        "tests": tests,
    }
    EVIDENCE.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("G04 source upload, security, parsing, tenancy, and recovery matrix passed")


if __name__ == "__main__":
    main()
