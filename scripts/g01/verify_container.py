"""Verify and record the G01 isolated Worker image."""

from __future__ import annotations

import json
import subprocess

from instant_ppt_worker.paths import REPOSITORY_ROOT

IMAGE = "instant-ppt-worker:g01"
EVIDENCE = REPOSITORY_ROOT / "docs" / "evidence" / "g01-container.json"


def _docker(*arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-4000:])
    return result.stdout.strip()


def main() -> None:
    raw = _docker("image", "inspect", IMAGE)
    inspect = json.loads(raw)[0]
    image_id = inspect["Id"]
    user = inspect["Config"]["User"]
    environment = inspect["Config"].get("Env", [])
    forbidden = [
        item
        for item in environment
        if any(
            token in item.upper() for token in ("DATABASE", "POSTGRES", "REDIS", "MINIO", "SECRET")
        )
    ]
    if user not in {"10001:10001", "10001"}:
        raise AssertionError(f"container user is not the isolated account: {user}")
    if forbidden:
        raise AssertionError(f"business credentials leaked into image config: {forbidden}")
    identity = _docker(
        "run",
        "--rm",
        "--entrypoint",
        "python",
        IMAGE,
        "-c",
        "import os; print(f'{os.getuid()}:{os.getgid()}')",
    )
    if identity != "10001:10001":
        raise AssertionError(f"runtime identity mismatch: {identity}")
    _docker("run", "--rm", IMAGE, "--help")
    _docker(
        "run",
        "--rm",
        "--entrypoint",
        "python",
        IMAGE,
        "/app/vendor/ppt-master/scripts/attribution_guard.py",
    )
    reference_smoke = json.loads(
        _docker(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            IMAGE,
            "-c",
            (
                "import json; "
                "from instant_ppt_worker.ppt_master_references import "
                "executor_reference_manifest, spec_lock_contract_payload; "
                "contract = spec_lock_contract_payload(); "
                "manifest = executor_reference_manifest(''); "
                "print(json.dumps({"
                "'contractSchema': contract['schema'], "
                "'referenceCount': len(manifest['references']), "
                "'manifestSha256': manifest['manifestSha256']"
                "}))"
            ),
        )
    )
    if reference_smoke["contractSchema"] != "instant-ppt.spec-lock-contract.v1":
        raise AssertionError("PPT-Master Spec Lock contract smoke returned the wrong schema")
    if reference_smoke["referenceCount"] < 5:
        raise AssertionError("PPT-Master Executor reference manifest is incomplete")
    evidence = {
        "schemaVersion": 1,
        "verifiedAt": "2026-08-16T00:00:00Z",
        "image": IMAGE,
        "imageId": image_id,
        "platform": inspect.get("Architecture", "unknown"),
        "runtimeUser": user,
        "runtimeIdentity": identity,
        "adapterHelp": "passed",
        "attributionGuard": "passed",
        "pptMasterReferenceContract": reference_smoke,
        "forbiddenCredentialEnvCount": len(forbidden),
        "baseImages": [
            {
                "name": "python:3.12.4-slim-bookworm",
                "indexDigest": (
                    "sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85"
                ),
                "linuxAmd64Digest": (
                    "sha256:a074fac67aa01841fee592d00bae14d25dcaf98ef6e12a683ecceb7e0147e2d1"
                ),
            },
            {
                "name": "ghcr.io/astral-sh/uv:0.12.5",
                "indexDigest": (
                    "sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1"
                ),
                "linuxAmd64Digest": (
                    "sha256:db2d5999728c5837e1bf9ba278ee6b05cef1e95e82a20e27b0c915cb4478b9d7"
                ),
            },
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"container: {IMAGE} {image_id} verified as non-root with attribution intact")


if __name__ == "__main__":
    main()
