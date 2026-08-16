"""Compare PowerPoint and WPS PNG exports for the ten G01 decks."""

from __future__ import annotations

import json
from pathlib import Path

from instant_ppt_worker.paths import REPOSITORY_ROOT
from PIL import Image, ImageChops, ImageStat

ROOT = REPOSITORY_ROOT / ".tmp" / "compatibility"
EVIDENCE = REPOSITORY_ROOT / "docs" / "evidence" / "g01-visual-diff.json"
EXPECTED_SIZE = (1280, 720)
MAX_MEAN_THRESHOLD = 8.0
MAX_RMS_THRESHOLD = 30.0


def _pngs(root: Path) -> list[Path]:
    return sorted(root.glob("*.PNG"), key=lambda path: path.name.casefold())


def main() -> None:
    powerpoint_cases = sorted(
        path.name for path in (ROOT / "powerpoint").iterdir() if path.is_dir()
    )
    wps_cases = sorted(path.name for path in (ROOT / "wps").iterdir() if path.is_dir())
    if powerpoint_cases != wps_cases or len(powerpoint_cases) != 10:
        raise AssertionError("PowerPoint/WPS export case rosters do not match the ten golden cases")
    results: list[dict[str, object]] = []
    for case in powerpoint_cases:
        powerpoint = _pngs(ROOT / "powerpoint" / case)
        wps = _pngs(ROOT / "wps" / case)
        if len(powerpoint) != 3 or len(wps) != 3:
            raise AssertionError(f"{case}: expected three PNG exports per application")
        for index, (powerpoint_path, wps_path) in enumerate(zip(powerpoint, wps, strict=True), 1):
            with Image.open(powerpoint_path) as source:
                powerpoint_image = source.convert("RGB")
            with Image.open(wps_path) as source:
                wps_image = source.convert("RGB")
            if powerpoint_image.size != EXPECTED_SIZE or wps_image.size != EXPECTED_SIZE:
                raise AssertionError(f"{case}/{index}: export dimensions differ from 1280x720")
            for application, image in (("PowerPoint", powerpoint_image), ("WPS", wps_image)):
                background = Image.new("RGB", image.size, image.getpixel((0, 0)))
                if ImageChops.difference(image, background).getbbox() is None:
                    raise AssertionError(f"{case}/{index}: {application} export is blank")
            difference = ImageChops.difference(powerpoint_image, wps_image)
            statistics = ImageStat.Stat(difference)
            mean = max(statistics.mean)
            rms = max(statistics.rms)
            if mean > MAX_MEAN_THRESHOLD or rms > MAX_RMS_THRESHOLD:
                raise AssertionError(
                    f"{case}/{index}: visual difference mean={mean:.3f}, "
                    f"rms={rms:.3f} exceeds threshold"
                )
            results.append(
                {
                    "case": case,
                    "slide": index,
                    "size": list(EXPECTED_SIZE),
                    "maxChannelMeanDifference": round(mean, 4),
                    "maxChannelRmsDifference": round(rms, 4),
                    "passed": True,
                }
            )
    evidence = {
        "schemaVersion": 1,
        "checkedAt": "2026-08-16T00:00:00Z",
        "comparisonCount": len(results),
        "passCount": len(results),
        "thresholds": {
            "maxChannelMeanDifference": MAX_MEAN_THRESHOLD,
            "maxChannelRmsDifference": MAX_RMS_THRESHOLD,
        },
        "observedMaxChannelMeanDifference": max(
            item["maxChannelMeanDifference"] for item in results
        ),
        "observedMaxChannelRmsDifference": max(item["maxChannelRmsDifference"] for item in results),
        "humanReviewStatus": "ready_for_review",
        "results": results,
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"visual: {len(results)}/30 PowerPoint-WPS PNG comparisons passed; "
        f"max mean={evidence['observedMaxChannelMeanDifference']}, "
        f"max rms={evidence['observedMaxChannelRmsDifference']}"
    )


if __name__ == "__main__":
    main()
