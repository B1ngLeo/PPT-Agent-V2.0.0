from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
from instant_ppt_domain.migrations import upgrade

TEST_DATABASE = "instant_ppt_g07_test"
TEST_DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@127.0.0.1:5432/"
    f"{TEST_DATABASE}"
)
ADMIN_DATABASE_URL = (
    "postgresql://instant_ppt:local-development-only@127.0.0.1:5432/postgres"
)


def _ensure_test_database() -> None:
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DATABASE,)
        ).fetchone()
        if exists is None:
            connection.execute(f'CREATE DATABASE "{TEST_DATABASE}"')


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    _ensure_test_database()
    upgrade(TEST_DATABASE_URL)
    environment = os.environ.copy()
    environment.setdefault("G07_TEST_DATABASE_URL", TEST_DATABASE_URL)
    # Keep the editor/export integration boundary hermetic while still exercising
    # the real Presentation Agent turn, tool, review, and publication runtime.
    environment["PLANNING_BACKEND"] = "fake"
    environment["TEXT_PROVIDER"] = "kimi"
    environment["KIMI_MODEL"] = "fake-agent@v1"
    environment["PRESENTATION_AUTHORING_MODE"] = "agent-authoring"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/integration/g07",
        "-q",
        "--basetemp",
        ".tmp/pytest-g07-integration",
        "--junitxml=docs/evidence/g07-editor-export-junit.xml",
    ]
    return subprocess.run(command, cwd=root, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
