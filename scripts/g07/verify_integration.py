from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.setdefault(
        "G07_TEST_DATABASE_URL",
        "postgresql+psycopg://instant_ppt:local-development-only@localhost:5432/instant_ppt",
    )
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
