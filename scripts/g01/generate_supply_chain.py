"""Generate normalized SBOM and font provenance evidence."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from instant_ppt_worker.paths import REPOSITORY_ROOT, VENDOR_ROOT

EVIDENCE_ROOT = REPOSITORY_ROOT / "docs" / "evidence"
FIXED_TIME = "2026-08-16T00:00:00Z"


def _run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-4000:])


def _normalize_sbom(path: Path) -> int:
    value = json.loads(path.read_text(encoding="utf-8"))
    value["serialNumber"] = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, path.name)}"
    metadata = value.setdefault("metadata", {})
    metadata["timestamp"] = FIXED_TIME
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(value.get("components", []))


def _component_names(path: Path) -> set[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return {str(component.get("name", "")).lower() for component in value.get("components", [])}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font_entry(name: str, windows_path: str, license_note: str) -> dict[str, object]:
    path = Path(windows_path)
    entry: dict[str, object] = {
        "family": name,
        "distribution": "not-bundled",
        "source": "client operating system",
        "licenseBoundary": license_note,
        "path": windows_path,
        "presentOnEvidenceHost": path.is_file(),
    }
    if path.is_file():
        entry["sha256"] = _sha256(path)
        entry["sizeBytes"] = path.stat().st_size
    return entry


def main() -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    python_sbom = EVIDENCE_ROOT / "sbom-python.cdx.json"
    node_sbom = EVIDENCE_ROOT / "sbom-node.cdx.json"
    base_python = str(getattr(sys, "_base_executable", sys.executable))
    _run(
        [
            base_python,
            "-m",
            "uv",
            "export",
            "--format",
            "cyclonedx1.5",
            "--preview-features",
            "sbom-export",
            "--frozen",
            "--output-file",
            str(python_sbom),
        ]
    )
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise RuntimeError("pnpm is not available")
    _run(
        [
            pnpm,
            "sbom",
            "--sbom-format",
            "cyclonedx",
            "--lockfile-only",
            "--out",
            str(node_sbom),
        ]
    )
    python_components = _normalize_sbom(python_sbom)
    node_components = _normalize_sbom(node_sbom)
    forbidden_python = _component_names(python_sbom) & {"pymupdf", "fitz", "ebooklib"}
    if forbidden_python:
        raise AssertionError(
            f"license-sensitive packages entered the Python SBOM: {forbidden_python}"
        )
    bundled_fonts = [
        path.relative_to(VENDOR_ROOT).as_posix()
        for path in VENDOR_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".ttf", ".ttc", ".otf", ".woff", ".woff2"}
    ]
    fonts = [
        _font_entry(
            "Arial",
            r"C:\Windows\Fonts\arial.ttf",
            "Microsoft/Windows-provided font; referenced by family name and never redistributed",
        ),
        _font_entry(
            "Microsoft YaHei",
            r"C:\Windows\Fonts\msyh.ttc",
            "Microsoft/Windows-provided font; referenced by family name and never redistributed",
        ),
        {
            "family": "sans-serif",
            "distribution": "generic-family",
            "source": "rendering environment",
            "licenseBoundary": "resolved by the host; no font bytes distributed",
        },
    ]
    manifest = {
        "schemaVersion": 1,
        "generatedAt": FIXED_TIME,
        "hostPlatform": platform.system(),
        "python": {
            "lockfile": "uv.lock",
            "sbom": "docs/evidence/sbom-python.cdx.json",
            "componentCount": python_components,
            "sha256": _sha256(python_sbom),
        },
        "node": {
            "lockfile": "pnpm-lock.yaml",
            "sbom": "docs/evidence/sbom-node.cdx.json",
            "componentCount": node_components,
            "sha256": _sha256(node_sbom),
        },
        "fonts": {
            "fontPackVersion": "system-safe-fonts@1",
            "bundledFontFiles": bundled_fonts,
            "bundledFontCount": len(bundled_fonts),
            "runtimeFamilies": fonts,
        },
        "licenseSensitiveExclusions": [
            {"component": "PyMuPDF", "status": "not-installed", "replacement": "pypdf==6.16.1"},
            {"component": "ebooklib", "status": "not-installed", "feature": "EPUB disabled"},
        ],
    }
    target = EVIDENCE_ROOT / "g01-supply-chain.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"supply-chain: Python {python_components} components, Node {node_components} components, "
        f"{len(bundled_fonts)} bundled fonts"
    )


if __name__ == "__main__":
    main()
