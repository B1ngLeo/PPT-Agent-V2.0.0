from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> int:
    e2e = _json("docs/evidence/g08-e2e-matrix.json")
    ids = {item["id"] for item in e2e["scenarios"] if item["status"] == "passed"}
    assert ids == {f"E2E-{index:03d}" for index in range(1, 13)}
    for item in e2e["scenarios"]:
        for evidence in item["evidence"]:
            assert (ROOT / evidence).is_file(), evidence

    browser = _json("docs/evidence/g08-final-browser-e2e.json")
    assert browser["result"] == "passed"
    assert browser["journey"]["generationStatus"] == "succeeded"
    assert browser["journey"]["currentRevisionNumber"] == 4
    assert browser["journey"]["slideCount"] == 8
    assert browser["pptxExport"]["boundRevisionId"] == browser["journey"][
        "currentRevisionId"
    ]
    assert browser["pptxExport"]["objectBytesAndHashMatched"] is True
    assert browser["pptxExport"]["serverSideEncryption"] == "AES256"
    assert browser["projectDataExport"]["objectBytesAndHashMatched"] is True
    assert browser["projectDataExport"]["serverSideEncryption"] == "AES256"
    assert browser["runtime"]["healthzStatus"] == 200
    assert browser["runtime"]["readyzStatus"] == 200
    assert browser["runtime"]["composeApiHealth"] == "healthy"
    assert browser["runtime"]["errorLogLines"] == 0
    assert all(
        browser["runtime"][field] is True
        for field in ("apiReadOnlyRoot", "workerReadOnlyRoot", "outboxReadOnlyRoot")
    )

    performance = _json("docs/evidence/performance/g08-api-baseline.json")
    assert performance["result"] == "passed" and performance["errors"] == 0
    assert performance["dataset"] == {
        "organizations": 100,
        "drafts": 1000,
        "jobEvents": 10000,
        "artifacts": 1000,
    }
    assert performance["profile"]["virtualUsers"] == 20
    assert performance["profile"]["warmupSeconds"] == 120
    assert performance["profile"]["measurementSeconds"] == 600
    assert performance["latency"]["read"]["p95Ms"] <= 300
    assert performance["latency"]["write"]["p95Ms"] <= 500

    recovery = _json("docs/evidence/recovery/g08-recovery-matrix.json")
    assert recovery["result"] == "passed" and len(recovery["scenarios"]) == 5
    assert all(
        item["status"] == "passed"
        and item["iterations"] == 10
        and item["seeds"] == list(range(10))
        and (ROOT / item["evidence"]).is_file()
        for item in recovery["scenarios"]
    )

    restore = _json("docs/evidence/operations/g08-backup-restore.json")
    assert restore["result"] == "passed"
    assert restore["postgres"]["countsAndSchemaMatched"] is True
    assert restore["postgres"]["source"] == restore["postgres"]["restored"]
    assert restore["objects"]["hashesMatched"] is True
    assert restore["objects"]["objectCount"] > 0

    governance = _json("docs/evidence/security/g08-object-governance.json")
    assert governance["result"] == "passed"
    assert governance["testDatabase"] == "instant_ppt_g08_test"
    assert governance["junit"]["tests"] == 4
    assert governance["junit"]["failures"] == 0
    assert governance["junit"]["skipped"] == 0
    assert governance["bucket"]["publicPolicy"] is False
    assert governance["bucket"]["defaultEncryption"] == "AES256"
    assert governance["bucket"]["lifecyclePrefix"] == "tenants/"
    assert governance["bucket"]["expiredDeleteMarkerCleanup"] is True
    assert governance["bucket"]["staleMultipartExpiry"] == "24h"
    assert governance["bucket"]["staleMultipartCleanupInterval"] == "1h"
    junit = ET.parse(ROOT / governance["junit"]["path"])
    assert len(junit.findall(".//testcase")) == 4

    security = _json("docs/evidence/security/g08-dependency-audit.json")
    assert security["result"] == "passed"
    assert security["node"]["advisoryCount"] == 0
    assert security["python"]["vulnerabilities"] == 0

    accessibility = _json("docs/evidence/accessibility/g08-axe-responsive.json")
    assert all(item["criticalSerious"] == 0 for item in accessibility["axe"]["states"])
    assert all(
        item["horizontalOverflow"] is False
        for item in accessibility["responsive"]["viewportChecks"]
    )
    assert accessibility["screenReader"]["status"] == "not_run"

    for document in (
        "docs/design/g08-observability-release.md",
        "docs/runbook.md",
        "docs/rollback.md",
        "docs/release-checklist.md",
        "docs/release-gate-report.md",
        "docs/privacy-and-provider-disclosure.md",
        "docs/evidence/g08-screen-reader-checklist.md",
    ):
        assert (ROOT / document).is_file(), document

    print(
        "G08 automated release evidence passed: E2E 12/12, recovery 5x10, "
        "performance/restore/security/accessibility ready; final human Gate status is "
        "verified separately from the Gate manifest"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
