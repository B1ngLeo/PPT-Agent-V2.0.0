from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from verify_runtime_deployment import RUNTIME_CONTRACT, verify

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_INPUTS = (
    ".python-version",
    "compose.yaml",
    "pyproject.toml",
    "uv.lock",
    "packages/domain",
    "services/api",
    "services/worker",
    "vendor/ppt-master",
)
RUNTIME_SERVICES = ("api", "worker", "agent-worker", "outbox", "provider-gateway")


def _run(
    *args: str,
    environment: dict[str, str] | None = None,
    capture: bool = False,
) -> str:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        env=environment,
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=capture,
    )
    return completed.stdout.strip() if capture else ""


def _runtime_changes() -> list[str]:
    output = _run(
        "git",
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *RUNTIME_INPUTS,
        capture=True,
    )
    return [line for line in output.splitlines() if line]


def _revision(*, allow_dirty: bool) -> tuple[str, list[str]]:
    head = _run("git", "rev-parse", "HEAD", capture=True).lower()
    changes = _runtime_changes()
    if changes and not allow_dirty:
        rendered = "\n".join(changes)
        raise RuntimeError(
            "runtime build inputs are uncommitted; commit them or explicitly use "
            f"--allow-dirty for a non-release diagnostic build:\n{rendered}"
        )
    if changes:
        return f"dev-{head[:12]}-dirty", changes
    return head, changes


def deploy(*, allow_dirty: bool, skip_build: bool, output: Path | None) -> dict:
    revision, changes = _revision(allow_dirty=allow_dirty)
    environment = {
        **os.environ,
        "APP_BUILD_REVISION": revision,
        "RUNTIME_CONTRACT_VERSION": RUNTIME_CONTRACT,
        # Compose Bake has been unreliable with the non-ASCII Windows workspace path.
        "COMPOSE_BAKE": "false",
    }
    compose = ("docker", "compose", "--profile", "runtime")
    if not skip_build:
        # The four worker-family services intentionally share this single image/tag.
        _run(*compose, "build", "api", environment=environment)
        _run(*compose, "build", "worker", environment=environment)
    _run(
        *compose,
        "up",
        "-d",
        "--force-recreate",
        "--wait",
        *RUNTIME_SERVICES,
        environment=environment,
    )
    result = verify(revision)
    result["dirtyRuntimeInputs"] = changes
    result["diagnosticDirtyBuild"] = bool(changes)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            __import__("json").dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build, recreate, and prove one coherent ISSUE-002 runtime deployment."
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow a diagnostic dev-<sha>-dirty image; never records a release SHA",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="recreate from an already-built image for the computed revision",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = deploy(
        allow_dirty=args.allow_dirty,
        skip_build=args.skip_build,
        output=args.output,
    )
    print(__import__("json").dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"runtime deployment failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
