from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[2]
    evidence_path = repository / "docs/evidence/g05-browser-e2e.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    responsive = evidence["responsive"]
    assertions = [
        evidence["result"] == "passed",
        evidence["journey"]["topicToApprovedBoundary"],
        evidence["journey"]["refreshRecoveredAllEdits"],
        evidence["journey"]["generationJobCount"] == 0,
        evidence["autosaveRecovery"]["localContentRetained"],
        evidence["autosaveRecovery"]["retryPersistedAfterReload"],
        evidence["revisionBehavior"]["stableSlideIds"],
        evidence["revisionBehavior"]["undoRedoCreateRevisions"],
        evidence["revisionBehavior"]["aiCreatesRevision"],
        evidence["approval"]["snapshotRemainsImmutableAfterEdit"],
        evidence["accessibility"]["nativeInteractiveElements"],
        evidence["accessibility"]["keyboardTextEntryAndFocus"],
        evidence["accessibility"]["dialogFocusRestored"],
        evidence["accessibility"]["minimumTouchTarget"] >= 44,
        evidence["consoleWarningsOrErrors"] == 0,
        all(not viewport["horizontalOverflow"] for viewport in responsive),
        {viewport["width"] for viewport in responsive} == {390, 900, 1440},
        any(viewport.get("assistantDrawerOperable") for viewport in responsive),
    ]
    if not all(assertions):
        raise SystemExit("G05 browser evidence failed one or more required assertions")
    print("G05 browser evidence: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
