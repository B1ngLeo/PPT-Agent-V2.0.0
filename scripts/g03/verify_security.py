"""Run fast G03 authentication and fail-closed security regression checks."""

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
            "packages/domain/tests/test_g03_security.py",
            "services/api/tests/test_g03_auth.py",
            "--basetemp",
            ".tmp/pytest-g03-security",
        ],
        cwd=ROOT,
        check=True,
    )
    print("G03 strict OIDC, production bypass, key, and audit checks passed")


if __name__ == "__main__":
    main()
