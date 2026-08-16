from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads(
        (root / "docs/evidence/g07-browser-e2e.json").read_text(encoding="utf-8")
    )
    assert evidence["schemaVersion"] == 1
    assert evidence["goal"] == "G07"
    assert evidence["result"] == "passed"

    journey = evidence["journey"]
    assert journey["initialSlideCount"] == 8
    assert journey["finalRevisionNumber"] >= 4
    assert journey["textEditPersistedAfterReload"] is True
    assert journey["stableSlideReordered"] is True
    assert journey["stableSlideRegenerated"] is True
    assert journey["oldReadyVisibleUntilQa"] is True
    assert journey["historyRestoredResultRoute"] is True

    export = evidence["export"]
    assert export["revisionId"] == journey["finalRevisionId"]
    assert export["pptxDownloaded"] is True and export["pptxBytes"] > 0
    assert export["projectDataDownloaded"] is True and export["projectDataBytes"] > 0
    assert export["editorRouteRetainedDuringDownloads"] is True
    assert export["crossTenantGrantStatus"] == 404

    accessibility = evidence["accessibility"]
    assert accessibility["mobileViewport"] == "390x844"
    assert all(
        accessibility[key] is True
        for key in (
            "mobileKeyControlsPresent",
            "semanticEditorRegionsPresent",
            "labeledRegenerationInstruction",
            "keyboardSkipLinkActivated",
            "defaultViewportRestored",
        )
    )

    deletion = evidence["deletion"]
    assert deletion["preDeleteDownloadStatus"] == 200
    assert deletion["deleteStatus"] == 204
    assert deletion["cleanupStatus"] == "succeeded"
    assert deletion["artifactCount"] == deletion["removedObjectCount"] == 22
    assert deletion["failedObjectCount"] == 0
    assert all(
        deletion[key] == 404
        for key in (
            "presentationAfterDelete",
            "generationJobAfterDelete",
            "sseAfterDelete",
            "oldSignedUrlAfterCleanup",
            "newGrantAfterDelete",
        )
    )
    print("G07 browser evidence: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
