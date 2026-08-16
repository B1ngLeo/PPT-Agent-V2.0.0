from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads(
        (root / "docs/evidence/g06-browser-e2e.json").read_text(encoding="utf-8")
    )
    assert evidence["schemaVersion"] == 1
    assert evidence["goal"] == "G06"
    assert evidence["result"] == "passed"
    journey = evidence["journey"]
    assert journey["approvalToRealJob"] is True
    assert journey["runningMonitorReloadRecovered"] is True
    assert journey["terminalMonitorReloadRecovered"] is True
    assert journey["status"] == "succeeded"
    assert journey["processor"] == "real"
    assert journey["readySlides"] == journey["totalSlides"] == 8
    assert journey["publicationVersion"] == 1
    publication = evidence["publication"]
    assert publication["generationArtifactCount"] == 13
    assert publication["publicationCount"] == 1
    assert publication["presentationRevisionCount"] == 1
    assert publication["slideVersionCount"] == 8
    assert publication["usage"]["slides"] == 8
    assert publication["usage"]["images"] == 0
    assert set(publication["coreArtifactKindsVisible"]) == {
        "generation_baseline_pptx",
        "generation_manifest",
        "generation_preview_svg",
        "generation_qa_report",
        "generation_source_bundle",
    }
    fidelity = evidence["contentFidelityRegression"]
    assert fidelity["detectedByProductionJourney"] is True
    assert fidelity["svgQaRegressionPassed"] is True
    assert fidelity["pptxEditableTextRegressionPassed"] is True
    assert fidelity["freshEightSlideJourneyPassedOnAttemptOne"] is True
    print("G06 browser evidence: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
