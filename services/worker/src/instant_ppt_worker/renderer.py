"""Fixed DeckPlan to SVG, upstream QA, native PPTX, preview, and manifest."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.content_quality import evaluate_deck
from instant_ppt_worker.errors import (
    CONTENT_QA_FAILED,
    PACKAGE_FAILED,
    QA_FAILED,
    RENDER_FAILED,
    AdapterError,
)
from instant_ppt_worker.models import DeckPlan
from instant_ppt_worker.package_qa import inspect_pptx, write_package_report
from instant_ppt_worker.paths import ENGINE_SCRIPTS
from instant_ppt_worker.settings import WorkerContract
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.svg_author import author_chart_slide, author_deck, author_slide


def _svg_visible_text(svg_paths: list[Path]) -> str:
    values: list[str] = []
    for path in svg_paths:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "text":
                continue
            value = "".join(element.itertext()).strip()
            if value:
                values.append(value)
    return "\n".join(values)


def _normalize_office_zip(payload: bytes, *, normalize_slides: bool) -> bytes:
    with zipfile.ZipFile(BytesIO(payload)) as source:
        members = []
        for info in source.infolist():
            data = source.read(info)
            if normalize_slides and info.filename.startswith(
                "ppt/slides/slide"
            ) and info.filename.endswith(".xml"):
                data = data.replace(b"<a:spAutoFit/>", b"<a:noAutofit/>")
            if info.filename == "docProps/core.xml":
                data = re.sub(
                    rb"(<dcterms:(?:created|modified)\b[^>]*>)[^<]*(</dcterms:(?:created|modified)>)",
                    rb"\g<1>2026-08-16T00:00:00Z\g<2>",
                    data,
                )
            elif normalize_slides and info.filename.startswith(
                "ppt/embeddings/"
            ) and info.filename.endswith(".xlsx"):
                data = _normalize_office_zip(data, normalize_slides=False)
            members.append((info.filename, data, info.compress_type, info.external_attr))
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for name, data, compression, external_attr in sorted(members):
            info = zipfile.ZipInfo(name, (2026, 8, 16, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = external_attr
            target.writestr(info, data)
    return buffer.getvalue()


def _normalize_pptx_zip(path: Path) -> None:
    """Stabilize editable content and nested Office package metadata."""

    path.write_bytes(_normalize_office_zip(path.read_bytes(), normalize_slides=True))


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


def render_slide_candidate(
    deck: DeckPlan,
    output_dir: Path,
    *,
    visual_index: int,
) -> dict[str, Path]:
    """Author and upstream-QA one slide without compiling a temporary PPTX."""

    if len(deck.slides) != 1:
        raise AdapterError(RENDER_FAILED, "slide candidate requires exactly one DeckPlan slide")
    content_report = evaluate_deck(deck, stage="slide-candidate")
    if not content_report["passed"]:
        raise AdapterError(
            CONTENT_QA_FAILED,
            json.dumps(content_report, ensure_ascii=False, separators=(",", ":"))[-4000:],
        )
    svg_dir = output_dir / "svg_output"
    validation_dir = output_dir / "validation"
    svg_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    svg_path = svg_dir / "slide_01.svg"
    author_slide(deck.slides[0], deck.title, visual_index, svg_path)
    qa_path = validation_dir / "svg_quality_report.json"
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
            str(qa_path),
            "--quick-generate",
        ],
        QA_FAILED,
    )
    return {"svg": svg_path, "qa": qa_path}


def render_deck(
    deck_plan_path: Path,
    output_dir: Path,
    *,
    organization_id: str,
    created_at: str,
    cover_image_path: Path | None = None,
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

    content_report = evaluate_deck(deck, stage="pre-render")
    if not content_report["passed"]:
        raise AdapterError(
            CONTENT_QA_FAILED,
            json.dumps(content_report, ensure_ascii=False, separators=(",", ":"))[-4000:],
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    materialized_cover = cover_image_path
    if cover_image_path is not None:
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        materialized_cover = images_dir / cover_image_path.name
        if materialized_cover.resolve() != cover_image_path.resolve():
            shutil.copyfile(cover_image_path, materialized_cover)
    svg_paths = author_deck(deck, output_dir, cover_image_path=materialized_cover)
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
    final_svg_digest = hashlib.sha256()
    for path in svg_paths:
        final_svg_digest.update(path.name.encode("utf-8"))
        final_svg_digest.update(path.read_bytes())
    final_content_report = evaluate_deck(
        deck,
        stage="final-svg",
        subject_sha256=final_svg_digest.hexdigest(),
        represented_text=_svg_visible_text(svg_paths),
    )
    final_content_path = validation_dir / "content-final-svg.json"
    final_content_path.write_bytes(
        json.dumps(
            final_content_report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if not final_content_report["passed"]:
        raise AdapterError(CONTENT_QA_FAILED, "legacy final SVG content gate failed")
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
    pptx_content_report = evaluate_deck(
        deck,
        stage="compiled-pptx",
        subject_sha256=sha256_file(pptx_path),
        representation_verified=True,
    )
    pptx_content_path = validation_dir / "content-pptx.json"
    pptx_content_path.write_bytes(
        json.dumps(
            pptx_content_report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if not pptx_content_report["passed"]:
        raise AdapterError(CONTENT_QA_FAILED, "legacy compiled PPTX content gate failed")

    preview = output_dir / "preview.svg"
    shutil.copyfile(svg_paths[0], preview)
    qa_report = {
        "schemaVersion": 1,
        "reportId": deterministic_ulid(sha256_file(upstream_qa)),
        "subjectType": "deck",
        "subjectId": deck.snapshot_id,
        "profile": "quick-engineering",
        "quickGenerate": True,
        "passed": all(
            report["passed"]
            for report in (content_report, final_content_report, pptx_content_report)
        )
        and package_report["passed"],
        "findings": package_report["findings"],
        "contentQa": {
            "preRender": content_report,
            "finalSvg": final_content_report,
            "compiledPptx": pptx_content_report,
        },
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
        "engineProfile": "quick-engineering",
        "quickGenerate": True,
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
            final_content_path,
            pptx_content_path,
            preview,
            qa_report_path,
            manifest_path,
            *extra_reports,
        ],
    }


def render_revision_deck(
    deck: DeckPlan,
    output_dir: Path,
    *,
    chart_specs: dict[str, dict[str, Any]],
    evidence_map: dict[str, Any],
    source_fragments: list[dict[str, Any]],
    source_manifest_sha256: str,
    effective_spec_revision_id: str,
    effective_spec_sha256: str,
    spec_lock_sha256: str,
    organization_id: str,
    created_at: str,
) -> dict[str, object]:
    """Run the non-Quick final gates for an Effective Design Spec revision."""

    bindings = {
        "effectiveSpecRevisionId": effective_spec_revision_id,
        "effectiveSpecInputSha256": effective_spec_sha256,
        "specLockSha256": spec_lock_sha256,
        "sourceManifestSha256": source_manifest_sha256,
        "evidenceMapSha256": evidence_map["evidenceMapSha256"],
    }
    pre_render = evaluate_deck(
        deck,
        stage="revision-pre-render",
        subject_sha256=effective_spec_sha256,
        evidence_map=evidence_map,
        source_fragments=source_fragments,
        source_manifest_sha256=source_manifest_sha256,
    )
    if not pre_render["passed"]:
        raise AdapterError(
            CONTENT_QA_FAILED,
            json.dumps(pre_render, ensure_ascii=False, separators=(",", ":"))[-4000:],
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "spec_lock.md").write_text(
        "\n".join(
            [
                "<!-- ppt-master-schema: spec-lock/v1 -->",
                "# Effective Revision Execution Lock",
                f"<!-- effective-spec-revision-id: {effective_spec_revision_id} -->",
                f"<!-- effective-spec-input-sha256: {effective_spec_sha256} -->",
                f"<!-- source-manifest-sha256: {source_manifest_sha256} -->",
                f"<!-- authoritative-spec-lock-sha256: {spec_lock_sha256} -->",
                "",
                "## canvas",
                "- viewBox: 0 0 1280 720",
                "- format: ppt169",
                "",
                "## colors",
                "- background: #F8FAFC",
                "- secondary_background: #E2E8F0",
                "- primary: #0F172A",
                "- accent: #2563EB",
                "- secondary_accent: #0F766E",
                "- body_text: #1E293B",
                "",
                "## typography",
                "- font_family: Microsoft YaHei, Arial, sans-serif",
                "- title_family: Microsoft YaHei, Arial, sans-serif",
                "- body_family: Microsoft YaHei, Arial, sans-serif",
                "- data_family: Arial, Microsoft YaHei, sans-serif",
                "- body: 22",
                "- title: 38",
                "- subtitle: 24",
                "- annotation: 15",
                "- data: 18",
                "",
                "## pptx_structure",
                "- mode: flat",
                "",
            ]
        ),
        encoding="utf-8",
    )
    svg_dir = output_dir / "svg_output"
    validation_dir = output_dir / "validation"
    svg_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = validation_dir / "revision-evidence-map.json"
    evidence_path.write_bytes(
        json.dumps(
            evidence_map,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    svg_paths: list[Path] = []
    for index, slide in enumerate(sorted(deck.slides, key=lambda value: value.order), start=1):
        path = svg_dir / f"slide_{index:02d}.svg"
        chart = chart_specs.get(slide.slide_id)
        if chart:
            author_chart_slide(
                slide,
                path,
                chart=[
                    (str(value["label"]), float(value["value"]))
                    for value in chart["values"]
                ],
                unit=str(chart["unit"]),
            )
        else:
            author_slide(slide, deck.title, index - 1, path)
        svg_paths.append(path)

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
        ],
        QA_FAILED,
        timeout=240,
    )
    roster_digest = hashlib.sha256()
    for path in svg_paths:
        roster_digest.update(path.name.encode("utf-8"))
        roster_digest.update(path.read_bytes())
    final_svg_sha256 = roster_digest.hexdigest()
    final_content = evaluate_deck(
        deck,
        stage="revision-final-svg",
        subject_sha256=final_svg_sha256,
        evidence_map=evidence_map,
        source_fragments=source_fragments,
        source_manifest_sha256=source_manifest_sha256,
        represented_text=_svg_visible_text(svg_paths),
    )
    final_content_path = validation_dir / "content-final-svg.json"
    final_content_path.write_bytes(
        json.dumps(
            final_content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if not final_content["passed"]:
        raise AdapterError(CONTENT_QA_FAILED, "revision final SVG content gate failed")
    if chart_specs:
        checks = []
        for slide_id, chart in sorted(chart_specs.items()):
            values = ",".join(
                f"{value['label']}:{float(value['value']):g}" for value in chart["values"]
            )
            calculated = _run(
                [
                    sys.executable,
                    str(ENGINE_SCRIPTS / "svg_position_calculator.py"),
                    "calc",
                    "bar",
                    "--data",
                    values,
                    "--area",
                    "180,230,1120,560",
                    "--bar-width",
                    "160",
                ],
                QA_FAILED,
                timeout=60,
            )
            checks.append(
                {
                    "slideId": slide_id,
                    "objectKey": chart["objectKey"],
                    "calculatorOutputSha256": hashlib.sha256(
                        calculated.stdout.encode("utf-8")
                    ).hexdigest(),
                }
            )
        (validation_dir / "chart-verification.json").write_bytes(
            json.dumps(
                {
                    "schema": "instant-ppt.verify-charts.v1",
                    "subjectSha256": final_svg_sha256,
                    "objects": checks,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    _run(
        [sys.executable, str(ENGINE_SCRIPTS / "finalize_svg.py"), str(output_dir)],
        RENDER_FAILED,
        timeout=240,
    )
    pptx_path = output_dir / "deck.pptx"
    _run(
        [
            sys.executable,
            str(ENGINE_SCRIPTS / "svg_to_pptx.py"),
            str(output_dir),
            "--format",
            "ppt169",
            "--output",
            str(pptx_path),
            "--no-notes",
            "--native-charts-and-tables",
        ],
        RENDER_FAILED,
        timeout=360,
    )
    if not pptx_path.is_file():
        raise AdapterError(RENDER_FAILED, "revision exporter returned without a PPTX")
    _normalize_pptx_zip(pptx_path)
    package_report = inspect_pptx(pptx_path, deck)
    package_report_path = validation_dir / "pptx-package-qa.json"
    write_package_report(package_report_path, package_report)
    if not package_report["passed"]:
        raise AdapterError(
            PACKAGE_FAILED,
            json.dumps(package_report["findings"], ensure_ascii=False),
        )
    pptx_sha256 = sha256_file(pptx_path)
    pptx_content = evaluate_deck(
        deck,
        stage="revision-compiled-pptx",
        subject_sha256=pptx_sha256,
        evidence_map=evidence_map,
        source_fragments=source_fragments,
        source_manifest_sha256=source_manifest_sha256,
        representation_verified=True,
    )
    pptx_content_path = validation_dir / "content-pptx.json"
    pptx_content_path.write_bytes(
        json.dumps(
            pptx_content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    reports = [pre_render, final_content, pptx_content]
    qa_report = {
        "schemaVersion": 2,
        "reportId": deterministic_ulid(sha256_file(upstream_qa)),
        "subjectType": "effective-design-spec-revision",
        "subjectId": deck.snapshot_id,
        "profile": "default-agentic-revision",
        "quickGenerate": False,
        "bindings": bindings,
        "passed": all(report["passed"] for report in reports) and package_report["passed"],
        "contentQa": {
            "preRender": pre_render,
            "finalSvg": final_content,
            "compiledPptx": pptx_content,
        },
        "checkedAt": created_at,
    }
    qa_report_path = output_dir / "qa-report.json"
    qa_report_path.write_bytes(
        json.dumps(
            qa_report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return {
        "pptx": pptx_path,
        "qa": qa_report_path,
        "packageQa": package_report_path,
        "finalContentQa": final_content_path,
        "pptxContentQa": pptx_content_path,
        "evidenceMap": evidence_path,
        "svgPaths": svg_paths,
        "organizationId": organization_id,
    }
