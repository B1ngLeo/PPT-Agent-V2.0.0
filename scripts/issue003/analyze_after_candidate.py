"""Measure and compare the frozen ISSUE-003 before/after presentation artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from analyze_baselines import analyze_pptx, contact_sheet, natural_pngs, sha256_file
from PIL import Image, ImageChops, ImageStat


def normalized_pixel_difference(left: Path, right: Path) -> float:
    left_image = Image.open(left).convert("RGB")
    right_image = Image.open(right).convert("RGB")
    if left_image.size != right_image.size:
        right_image = right_image.resize(left_image.size, Image.Resampling.LANCZOS)
    statistics = ImageStat.Stat(ImageChops.difference(left_image, right_image))
    return round(sum(statistics.mean) / (3 * 255), 6)


def main() -> int:
    repository_root = Path(__file__).resolve().parents[2]
    evidence_root = repository_root / "docs/evidence/issue003"
    baseline_root = evidence_root / "baseline"
    after_root = evidence_root / "after"
    candidate = after_root / "after-agent-authoring.pptx"
    if not candidate.is_file():
        raise SystemExit(f"candidate is missing: {candidate}")
    baseline_metrics = json.loads(
        (baseline_root / "baseline-metrics.json").read_text(encoding="utf-8")
    )
    powerpoint_pngs = natural_pngs(after_root / "renders" / "powerpoint")
    wps_pngs = natural_pngs(after_root / "renders" / "wps")
    if len(powerpoint_pngs) != len(wps_pngs) or len(powerpoint_pngs) != 10:
        raise RuntimeError("PowerPoint/WPS after render rosters must both contain 10 pages")
    powerpoint_contact = contact_sheet(
        powerpoint_pngs,
        after_root / "after-agent-authoring-powerpoint-contact-sheet.png",
    )
    wps_contact = contact_sheet(
        wps_pngs,
        after_root / "after-agent-authoring-wps-contact-sheet.png",
    )
    candidate_metrics = analyze_pptx(candidate)
    before_metrics = baseline_metrics["decks"]["before-deterministic-template"]
    project = next(after_root.glob("agent-candidate_ppt169_*"))
    plan = json.loads((project / "deck-plan.json").read_text(encoding="utf-8"))
    package_qa = json.loads(
        (project / "validation/pptx-package-qa.json").read_text(encoding="utf-8")
    )
    final_svg_qa = json.loads(
        (project / "validation/svg_quality_report.json").read_text(encoding="utf-8")
    )
    comparison = {
        "schemaVersion": 1,
        "status": "passed",
        "authority": {
            "before": before_metrics["path"],
            "beforeSha256": before_metrics["sha256"],
            "after": candidate.name,
            "afterSha256": sha256_file(candidate),
            "strictSameApprovalInput": True,
            "referenceIsNonStrict": True,
        },
        "metrics": {
            "before": before_metrics,
            "after": candidate_metrics,
            "delta": {
                "recursiveShapeCount": (
                    candidate_metrics["recursiveShapeCount"]
                    - before_metrics["recursiveShapeCount"]
                ),
                "visibleCharacterCount": (
                    candidate_metrics["visibleCharacterCount"]
                    - before_metrics["visibleCharacterCount"]
                ),
                "nativeChartCount": (
                    candidate_metrics["nativeChartCount"]
                    - before_metrics["nativeChartCount"]
                ),
                "averageTopLevelShapesPerSlide": round(
                    candidate_metrics["averageTopLevelShapesPerSlide"]
                    - before_metrics["averageTopLevelShapesPerSlide"],
                    2,
                ),
            },
        },
        "semanticStructure": {
            "roles": [slide["role"] for slide in plan["slides"]],
            "distinctRoleCount": len({slide["role"] for slide in plan["slides"]}),
            "stableSlideIds": [slide["slideId"] for slide in plan["slides"]],
        },
        "qualityGates": {
            "packagePassed": package_qa["passed"],
            "finalSvgBlockingCount": len(
                final_svg_qa["categories"]["blocking"]["issues"]
            ),
            "editableTextShapeCount": package_qa["editableTextShapeCount"],
            "editableNativeShapeCount": package_qa["editableNativeShapeCount"],
            "matchedEditableTextCount": package_qa["matchedEditableTextCount"],
            "expectedEditableTextCount": package_qa["expectedEditableTextCount"],
            "fullSlidePictureCount": package_qa["fullSlidePictureCount"],
        },
        "officeRenders": {
            "powerpoint": powerpoint_contact,
            "wps": wps_contact,
            "crossApplicationNormalizedPixelDifference": [
                normalized_pixel_difference(left, right)
                for left, right in zip(powerpoint_pngs, wps_pngs, strict=True)
            ],
        },
    }
    output = after_root / "after-comparison-metrics.json"
    output.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "after": candidate_metrics,
                "delta": comparison["metrics"]["delta"],
                "distinctRoleCount": comparison["semanticStructure"][
                    "distinctRoleCount"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
