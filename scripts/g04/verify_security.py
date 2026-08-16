"""Run the fast G04 source intake and scanner security checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "packages/domain/tests/test_g04_sources.py",
            "services/worker/tests/test_source_pipeline.py",
            "services/worker/tests/test_security.py",
            "--basetemp",
            ".tmp/pytest-g04-security",
        ],
        cwd=ROOT,
        check=True,
    )
    print("G04 upload validation, clamd protocol, and fail-closed checks passed")


if __name__ == "__main__":
    main()
