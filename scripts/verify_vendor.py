"""Verify the fixed ppt-master vendor snapshot without modifying upstream files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = REPOSITORY_ROOT / "vendor" / "ppt-master"
MANIFEST_PATH = REPOSITORY_ROOT / "vendor" / "ppt-master.vendor.json"


def sha256(path: Path) -> str:
    """Return a lowercase SHA-256 for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_tree_sha256(root: Path) -> str:
    """Hash sorted relative paths and content hashes into a portable tree digest."""
    digest = hashlib.sha256()
    source_files = (
        item
        for item in root.rglob("*")
        if item.is_file()
        and "__pycache__" not in item.parts
        and item.suffix.lower() not in {".pyc", ".pyo"}
    )
    for path in sorted(source_files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def verify() -> None:
    """Fail when provenance, attribution, or the immutable snapshot has drifted."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["tag"] != "v4.7.0":
        raise RuntimeError("unexpected ppt-master tag")
    if manifest["commit"] != "e8323bfaee249cffe1301ec40fca5875eb544d46":
        raise RuntimeError("unexpected ppt-master commit")
    if (VENDOR_ROOT / ".git").exists():
        raise RuntimeError("vendor snapshot must not contain nested Git metadata")

    actual_tree = canonical_tree_sha256(VENDOR_ROOT)
    if actual_tree != manifest["canonicalTreeSha256"]:
        raise RuntimeError(f"vendor tree digest mismatch: {actual_tree}")

    for relative, expected in manifest["protectedFiles"].items():
        path = VENDOR_ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"missing protected vendor file: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"protected vendor file changed: {relative}: {actual}")

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(VENDOR_ROOT / "scripts" / "attribution_guard.py")],
        cwd=VENDOR_ROOT,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"upstream attribution guard failed: {result.returncode}")

    print(
        "vendor: ppt-master v4.7.0 "
        "(e8323bfaee249cffe1301ec40fca5875eb544d46) attribution and tree verified"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-tree-hash", action="store_true")
    args = parser.parse_args()
    if args.print_tree_hash:
        print(canonical_tree_sha256(VENDOR_ROOT))
        return 0
    verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
