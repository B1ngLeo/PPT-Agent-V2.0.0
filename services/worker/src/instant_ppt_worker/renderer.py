"""Fixed DeckPlan to SVG, upstream QA, native PPTX, preview, and manifest."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path

from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.errors import PACKAGE_FAILED, QA_FAILED, RENDER_FAILED, AdapterError
from instant_ppt_worker.models import DeckPlan
from instant_ppt_worker.package_qa import inspect_pptx, write_package_report
from instant_ppt_worker.paths import ENGINE_SCRIPTS
from instant_ppt_worker.settings import WorkerContract
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.svg_author import author_deck


def _normalize_pptx_zip(path: Path) -> None:
    """Stabilize editable text layout and remove wall-clock ZIP metadata."""

    with zipfile.ZipFile(path) as source:
        members = []
        for info in source.infolist():
            data = source.read(info)
            if info.filename.startswith("ppt/slides/slide") and info.filename.endswith(".xml"):
                data = data.replace(b"<a:spAutoFit/>", b"<a:noAutofit/>")
            elif info.filename == "docProps/core.xml":
                data = re.sub(
                    rb"(<dcterms:(?:created|modified)\b[^>]*>)[^<]*(</dcterms:(?:created|modified)>)",
                    rb"\g<1>2026-08-16T00:00:00Z\g<2>",
                    data,
                )
            members.append((info.filename, data, info.compress_type, info.external_attr))
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for name, data, compression, external_attr in sorted(members):
            info = zipfile.ZipInfo(name, (2026, 8, 16, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = external_attr
            target.writestr(info, data)
    path.write_bytes(buffer.getvalue())


def _run(command: list[str], code: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "engine command failed").strip()
        raise AdapterError(code, message[-2000:])
    return result


def render_deck(
    deck_plan_path: Path,
    output_dir: Path,
    *,
    organization_id: str,
    created_at: str,
) -> dict[str, object]:
    try:
        deck = DeckPlan.model_validate_json(deck_plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdapterError(RENDER_FAILED, f"DeckPlan validation failed: {exc}") from exc
    orders = [slide.order for slide in deck.slides]
    if sorted(orders) != list(range(len(deck.slides))) or len(set(orders)) != len(orders):
        raise AdapterError(RENDER_FAILED, "DeckPlan slide orders must be contiguous and unique")
    if not all(slide.editable for slide in deck.slides):
        raise AdapterError(RENDER_FAILED, "G01 native baseline requires every slide to be editable")

    output_dir.mkdir(parents=True, exist_ok=True)
    svg_paths = author_deck(deck, output_dir)
    validation_dir = output_dir / "validation"
    validation_dir.mkdir(exist_ok=True)
    upstream_qa = validation_dir / "svg_quality_report.json"
    _run(
        [
            sys.executable,
            str(ENGINE_SCRIPTS / "svg_quality_checker.py"),
            str(output_dir),
            "--format",
            "ppt169",
            "--stage",
            "final",
            "--json-output",
            str(upstream_qa),
            "--quick-generate",
        ],
        QA_FAILED,
    )
    pptx_path = output_dir / "deck.pptx"
    _run(
        [
            sys.executable,
            str(ENGINE_SCRIPTS / "svg_to_pptx.py"),
            str(output_dir),
            "--quick-generate",
            "--format",
            "ppt169",
            "--output",
            str(pptx_path),
            "--no-notes",
            "--no-animations",
        ],
        RENDER_FAILED,
        timeout=300,
    )
    if not pptx_path.is_file():
        raise AdapterError(RENDER_FAILED, "engine returned success without a PPTX artifact")
    _normalize_pptx_zip(pptx_path)

    package_report = inspect_pptx(pptx_path, deck)
    package_report_path = validation_dir / "pptx-package-qa.json"
    write_package_report(package_report_path, package_report)
    if not package_report["passed"]:
        raise AdapterError(
            PACKAGE_FAILED, json.dumps(package_report["findings"], ensure_ascii=False)
        )

    preview = output_dir / "preview.svg"
    shutil.copyfile(svg_paths[0], preview)
    qa_report = {
        "schemaVersion": 1,
        "reportId": deterministic_ulid(sha256_file(upstream_qa)),
        "subjectType": "deck",
        "subjectId": deck.snapshot_id,
        "passed": True,
        "findings": package_report["findings"],
        "checkedAt": created_at,
    }
    qa_report_path = output_dir / "qa-report.json"
    qa_report_path.write_text(
        json.dumps(qa_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pptx_sha = sha256_file(pptx_path)
    manifest = {
        "schemaVersion": 1,
        "artifactId": deterministic_ulid(pptx_sha),
        "organizationId": organization_id,
        "artifactType": "generation_baseline_pptx",
        "objectKey": "deck.pptx",
        "sha256": pptx_sha,
        "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "sizeBytes": pptx_path.stat().st_size,
        "engineVersion": WorkerContract().engine_version,
        "fontPackVersion": "system-safe-fonts@1",
        "snapshotId": deck.snapshot_id,
        "presentationRevisionId": None,
        "createdAt": created_at,
    }
    manifest_path = output_dir / "artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    extra_reports = sorted(validation_dir.glob("*.report.json"))
    return {
        "deck": deck,
        "paths": [
            *svg_paths,
            upstream_qa,
            pptx_path,
            package_report_path,
            preview,
            qa_report_path,
            manifest_path,
            *extra_reports,
        ],
    }
