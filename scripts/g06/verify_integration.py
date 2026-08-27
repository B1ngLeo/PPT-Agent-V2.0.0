from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
from instant_ppt_domain.migrations import upgrade

TEST_DATABASE = "instant_ppt_g06_test"
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
    environment.setdefault("G06_TEST_DATABASE_URL", TEST_DATABASE_URL)
    # Exercise the real Agent turn/tool/reviewer runtime deterministically at the
    # integration boundary without requiring or transmitting a live Provider key.
    environment["PLANNING_BACKEND"] = "fake"
    environment["TEXT_PROVIDER"] = "kimi"
    environment["KIMI_MODEL"] = "fake-agent@v1"
    environment["PRESENTATION_AUTHORING_MODE"] = "agent-authoring"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/integration/g06",
        "-q",
        "--junitxml=docs/evidence/g06-generation-junit.xml",
    ]
    return subprocess.run(command, cwd=root, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
