from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed


def main() -> int:
    pnpm = shutil.which("pnpm")
    base_python = getattr(sys, "_base_executable", sys.executable)
    if pnpm is None:
        raise SystemExit("pnpm is required")

    node_result = _run(
        [pnpm, "audit", "--registry=https://registry.npmjs.org", "--prod", "--json"]
    )
    node = json.loads(node_result.stdout)
    advisories = node.get("advisories", {})
    metadata = node.get("metadata", {})

    python_result = _run(
        [
            base_python,
            "-m",
            "uv",
            "run",
            "--with",
            "pip-audit",
            "pip-audit",
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ]
    )
    python_payload = json.loads(python_result.stdout)
    dependencies = (
        python_payload.get("dependencies", [])
        if isinstance(python_payload, dict)
        else python_payload
    )
    vulnerable = [dependency for dependency in dependencies if dependency.get("vulns")]
    skipped = sorted(
        {
            dependency["name"]
            for dependency in dependencies
            if dependency.get("skip_reason")
        }
    )

    report = {
        "schemaVersion": 1,
        "goal": "G08",
        "generatedAt": datetime.now(UTC).isoformat(),
        "result": "passed" if not advisories and not vulnerable else "failed",
        "node": {
            "command": "pnpm audit --registry=https://registry.npmjs.org --prod --json",
            "advisoryCount": len(advisories),
            "vulnerabilities": metadata.get("vulnerabilities", {}),
            "dependencies": metadata.get("dependencies", 0),
        },
        "python": {
            "command": "uv run --with pip-audit pip-audit --format json --progress-spinner off",
            "dependencyCount": len(dependencies),
            "vulnerableDependencyCount": len(vulnerable),
            "vulnerabilities": sum(len(item["vulns"]) for item in vulnerable),
            "localWorkspacePackagesNotOnPyPI": skipped,
        },
        "notes": [
            "The configured npm mirror does not expose an audit endpoint; "
            "the official npm registry is used explicitly.",
            "Local workspace packages are not published on PyPI and are expected "
            "to be skipped by pip-audit.",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
