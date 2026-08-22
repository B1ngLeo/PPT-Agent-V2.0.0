from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.setdefault(
        "G06_TEST_DATABASE_URL",
        "postgresql+psycopg://instant_ppt:local-development-only@127.0.0.1:5432/instant_ppt",
    )
    # Exercise the real Agent turn/tool/reviewer runtime deterministically at the
    # integration boundary without requiring or transmitting a live Provider key.
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
