"""Read-only, hash-bound access to the pinned PPT Master contract authority."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from instant_ppt_worker.paths import VENDOR_ROOT

VENDOR_MANIFEST_PATH = VENDOR_ROOT.parent / "ppt-master.vendor.json"
SPEC_LOCK_REFERENCE = "templates/spec_lock_reference.md"
SPEC_LOCK_SCHEMA = "templates/schemas/spec_lock.schema.json"
DESIGN_SPEC_REFERENCE = "templates/design_spec_reference.md"
DESIGN_SPEC_SCHEMA = "templates/schemas/design_spec.schema.json"

EXECUTOR_BASE_REFERENCES = (
    "references/executor-base.md",
    "references/shared-standards-core.md",
    "references/semantic-svg.md",
    "references/svg-effects.md",
    "references/native-shape-authoring.md",
)

_REFERENCE_ALLOWLIST = frozenset(
    {
        DESIGN_SPEC_REFERENCE,
        DESIGN_SPEC_SCHEMA,
        SPEC_LOCK_REFERENCE,
        SPEC_LOCK_SCHEMA,
        *EXECUTOR_BASE_REFERENCES,
        "references/executor-chart.md",
        "references/executor-image.md",
        "references/executor-structure.md",
        "references/executor-structured.md",
        "references/executor-table.md",
        "references/native-data-interface.md",
        "references/pptx-structure-interface.md",
        "references/svg-image-embedding.md",
    }
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _vendor_version() -> dict[str, str]:
    manifest = json.loads(VENDOR_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        "engine": f"ppt-master@{manifest['tag']}",
        "tag": str(manifest["tag"]),
        "commit": str(manifest["commit"]),
        "treeSha256": str(manifest["canonicalTreeSha256"]),
    }


def read_ppt_master_reference(relative_path: str) -> dict[str, Any]:
    """Return one complete whitelisted vendored reference with provenance."""

    normalized = PurePosixPath(relative_path).as_posix()
    if normalized not in _REFERENCE_ALLOWLIST:
        raise ValueError("PPT Master reference path is not in the read-only allowlist")
    path = (VENDOR_ROOT / Path(*PurePosixPath(normalized).parts)).resolve()
    if not path.is_relative_to(VENDOR_ROOT.resolve()) or not path.is_file():
        raise ValueError("PPT Master reference is missing or escapes the pinned vendor tree")
    raw = path.read_bytes()
    return {
        "schema": "instant-ppt.ppt-master-reference.v1",
        "path": normalized,
        "sha256": _sha256_bytes(raw),
        "sizeBytes": len(raw),
        "version": _vendor_version(),
        "content": raw.decode("utf-8-sig"),
    }


def spec_lock_contract_payload() -> dict[str, Any]:
    return {
        "schema": "instant-ppt.spec-lock-contract.v1",
        "reference": read_ppt_master_reference(SPEC_LOCK_REFERENCE),
        "machineSchema": read_ppt_master_reference(SPEC_LOCK_SCHEMA),
    }


def executor_reference_paths(spec_lock: str) -> tuple[str, ...]:
    """Resolve the fixed base set plus only lock-triggered executor branches."""

    required = list(EXECUTOR_BASE_REFERENCES)
    if re.search(r"(?m)^## pptx_structure\s*$[\s\S]*?^- mode:\s*structured\s*$", spec_lock):
        required.extend(
            (
                "references/executor-structure.md",
                "references/executor-structured.md",
                "references/pptx-structure-interface.md",
            )
        )
    if re.search(r"(?m)^## images\s*$", spec_lock):
        required.extend(
            ("references/executor-image.md", "references/svg-image-embedding.md")
        )
    visualization_rows = re.findall(
        r"(?m)^- P\d{2,}:\s*(chart|table)/[a-z0-9_]+\s*$", spec_lock
    )
    if "chart" in visualization_rows:
        required.extend(
            ("references/executor-chart.md", "references/native-data-interface.md")
        )
    if "table" in visualization_rows:
        required.extend(
            ("references/executor-table.md", "references/native-data-interface.md")
        )
    return tuple(dict.fromkeys(required))


def executor_reference_manifest(spec_lock: str) -> dict[str, Any]:
    references = [
        {
            key: value
            for key, value in read_ppt_master_reference(path).items()
            if key != "content"
        }
        for path in executor_reference_paths(spec_lock)
    ]
    digest = hashlib.sha256(
        json.dumps(references, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "instant-ppt.ppt-master-reference-manifest.v1",
        "references": references,
        "manifestSha256": digest,
    }
