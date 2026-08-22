import json
from pathlib import Path

import pytest
from instant_ppt_worker.visual_review_runtime import (
    VisualReviewReport,
    blocking_pages,
)
from pydantic import ValidationError

WORKFLOW_RUN_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAA"
HASH = "a" * 64


def _report(*, passed: bool, issues: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "workflowRunId": WORKFLOW_RUN_ID,
        "reviewRound": 1,
        "subjectSha256": HASH,
        "renderSetSha256": HASH,
        "contactSheetSha256": HASH,
        "passed": passed,
        "issues": issues,
        "summary": "Strict visual review result.",
    }


def test_visual_review_pass_requires_zero_blocking_findings() -> None:
    blocking = {
        "issueId": "VR01",
        "category": "hierarchy",
        "severity": "blocking",
        "scope": "page",
        "pnn": "P01",
        "owner": "executor",
        "message": "The title and body have equal visual weight.",
        "region": "P01 title/body",
        "suggestedAction": "Increase title emphasis without changing copy.",
    }

    with pytest.raises(ValidationError, match="zero blocking"):
        VisualReviewReport.model_validate(_report(passed=True, issues=[blocking]))
    with pytest.raises(ValidationError, match="zero blocking"):
        VisualReviewReport.model_validate(_report(passed=False, issues=[]))


def test_deck_blocking_finding_expands_to_the_exact_roster() -> None:
    issue = {
        "issueId": "VR02",
        "category": "deck-consistency",
        "severity": "blocking",
        "scope": "deck",
        "pnn": None,
        "owner": "strategist",
        "message": "The visual system drifts between sections.",
        "region": "whole deck",
        "suggestedAction": "Restore the approved rhythm on every page.",
    }
    report = VisualReviewReport.model_validate(
        _report(passed=False, issues=[issue])
    ).model_dump(by_alias=True, mode="json")

    grouped = blocking_pages(report, ["P01", "P02", "P03"])

    assert list(grouped) == ["P01", "P02", "P03"]
    assert all(values == [issue] for values in grouped.values())


def test_materialized_visual_review_schema_matches_runtime_contract() -> None:
    path = Path("services/worker/contracts/visual-review.v1.schema.json")
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    generated = VisualReviewReport.model_json_schema()
    for key in ("$defs", "properties", "required", "title", "type"):
        assert on_disk[key] == generated[key]
