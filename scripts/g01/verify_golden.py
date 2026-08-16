"""Run the two G01 golden chains for all ten approved cases."""

from __future__ import annotations

import json
from pathlib import Path

from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.models import DeckPlan, SecurityDecision
from instant_ppt_worker.paths import REPOSITORY_ROOT
from instant_ppt_worker.renderer import render_deck
from instant_ppt_worker.security import scan_source
from instant_ppt_worker.source_parser import parse_source

GOLDEN_ROOT = REPOSITORY_ROOT / "tests" / "golden"
EVIDENCE_PATH = REPOSITORY_ROOT / "docs" / "evidence" / "g01-golden-results.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_case(case_root: Path) -> dict[str, object]:
    case = _load(case_root / "case.json")
    source_key = str(case["sourceKey"])
    source_path = case_root / source_key
    generated = case_root / "generated"
    decision_path = generated / "security-decision.json"
    decision = scan_source(source_key, source_path)
    if decision.decision != "clean":
        raise AssertionError(f"{case_root.name}: source rejected: {decision.findings}")
    SecurityDecision.model_validate(decision.model_dump())
    _write(decision_path, decision.model_dump(by_alias=True, mode="json"))
    parsed = parse_source(
        source_key,
        source_path,
        decision_path,
        generated / "parse",
        source_id=str(case["sourceId"]),
        organization_id=str(case["organizationId"]),
        created_at=str(case["createdAt"]),
    )
    expected_package = _load(case_root / "source-package.expected.json")
    if parsed["sourcePackage"] != expected_package:
        raise AssertionError(f"{case_root.name}: SourcePackage differs from approved baseline")

    deck_path = case_root / "deck-plan.approved.json"
    deck = DeckPlan.model_validate_json(deck_path.read_text(encoding="utf-8"))
    render_deck(
        deck_path,
        generated / "render",
        organization_id=str(case["organizationId"]),
        created_at=str(case["createdAt"]),
    )
    render_root = generated / "render"
    svg_qa = _load(render_root / "validation" / "svg_quality_report.json")
    package_qa = _load(render_root / "validation" / "pptx-package-qa.json")
    manifest = _load(render_root / "artifact-manifest.json")
    if svg_qa["summary"] != {
        "total": len(deck.slides),
        "passed": len(deck.slides),
        "warnings": 0,
        "errors": 0,
    }:
        raise AssertionError(f"{case_root.name}: SVG quality gate is not pristine")
    if package_qa["passed"] is not True:
        raise AssertionError(f"{case_root.name}: PPTX package QA failed")
    if package_qa["slideCount"] != len(deck.slides):
        raise AssertionError(f"{case_root.name}: PPTX slide count mismatch")
    if package_qa["editableTextShapeCount"] < len(deck.slides) * 2:
        raise AssertionError(f"{case_root.name}: editable text coverage is too low")
    if package_qa["matchedEditableTextCount"] != package_qa["expectedEditableTextCount"]:
        raise AssertionError(f"{case_root.name}: planned text is missing from editable shapes")
    if package_qa["editableNativeShapeCount"] < len(deck.slides):
        raise AssertionError(f"{case_root.name}: editable native shape coverage is too low")
    if package_qa["fullSlidePictureCount"] != 0:
        raise AssertionError(f"{case_root.name}: full-slide bitmap fallback detected")
    if package_qa["missingRelationshipTargets"]:
        raise AssertionError(f"{case_root.name}: PPTX contains dangling relationships")
    if package_qa["unreferencedMediaParts"]:
        raise AssertionError(f"{case_root.name}: PPTX contains unreferenced media")
    pptx_path = render_root / "deck.pptx"
    if manifest["sha256"] != sha256_file(pptx_path):
        raise AssertionError(f"{case_root.name}: manifest hash mismatch")
    preview_path = render_root / "preview.svg"
    if not preview_path.is_file() or "<svg" not in preview_path.read_text(encoding="utf-8")[:256]:
        raise AssertionError(f"{case_root.name}: preview SVG is missing or invalid")

    svg_hashes = [sha256_file(path) for path in sorted((render_root / "svg_output").glob("*.svg"))]
    return {
        "slug": case_root.name,
        "coverage": case["coverage"],
        "sourceSha256": expected_package["sourceSha256"],
        "sourcePackage": "passed",
        "svgQa": "passed",
        "pptxPackageQa": "passed",
        "slideCount": len(deck.slides),
        "editableTextShapeCount": package_qa["editableTextShapeCount"],
        "expectedEditableTextCount": package_qa["expectedEditableTextCount"],
        "matchedEditableTextCount": package_qa["matchedEditableTextCount"],
        "editableNativeShapeCount": package_qa["editableNativeShapeCount"],
        "fullSlidePictureCount": package_qa["fullSlidePictureCount"],
        "relationshipCount": package_qa["relationshipCount"],
        "mediaPartCount": len(package_qa["mediaParts"]),
        "mediaReferenceCount": len(package_qa["mediaReferences"]),
        "svgSha256": svg_hashes,
        "previewSha256": sha256_file(preview_path),
        "pptxSha256": manifest["sha256"],
    }


def main() -> None:
    cases = sorted(path for path in GOLDEN_ROOT.iterdir() if path.is_dir())
    if len(cases) != 10:
        raise SystemExit(f"golden: expected 10 cases, found {len(cases)}")
    results = [verify_case(case) for case in cases]
    evidence = {
        "schemaVersion": 1,
        "engineVersion": "ppt-master@v4.7.0+e8323bfa",
        "caseCount": len(results),
        "sourcePassCount": len(results),
        "renderPassCount": len(results),
        "results": results,
    }
    _write(EVIDENCE_PATH, evidence)
    print(f"golden: {len(results)}/10 source chains and {len(results)}/10 render chains passed")


if __name__ == "__main__":
    main()
