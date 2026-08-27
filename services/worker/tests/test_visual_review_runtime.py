import io
import json
from pathlib import Path

import pytest
from instant_ppt_worker.visual_review_runtime import (
    VisualReviewModelResult,
    VisualReviewReport,
    _materialize_batch_report,
    _merge_visual_review_reports,
    _visual_review_completion_limit,
    _visual_review_page_batches,
    adaptive_visual_review_decision,
    blocking_pages,
    effective_visual_severity,
    render_visual_assets,
    visual_review_metrics,
)
from PIL import Image
from pydantic import ValidationError

WORKFLOW_RUN_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAA"
HASH = "a" * 64
FINGERPRINT = "b" * 64


def test_visual_review_uses_a_dedicated_completion_cap() -> None:
    assert _visual_review_completion_limit(48_000) == 40_000
    assert _visual_review_completion_limit(1024) == 1024


def test_visual_review_batches_two_detailed_pages_per_multimodal_call() -> None:
    pages = [{"pnn": f"P{index:02d}"} for index in range(1, 6)]

    batches = _visual_review_page_batches(pages)

    assert [[page["pnn"] for page in batch] for batch in batches] == [
        ["P01", "P02"],
        ["P03", "P04"],
        ["P05"],
    ]


def test_visual_review_renders_final_direct_svg(tmp_path: Path) -> None:
    project = tmp_path / "project"
    svg_dir = project / "svg_output"
    svg_dir.mkdir(parents=True)
    (svg_dir / "slide_01.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720">'
        '<rect id="page-background" x="0" y="0" width="1280" height="720" fill="#FFFFFF"/>'
        '<rect id="direct-accent" x="100" y="100" width="400" height="200" fill="#E11D48"/>'
        "</svg>",
        encoding="utf-8",
    )

    render_set = render_visual_assets(project, review_round=1)

    page = render_set["pages"][0]
    assert page["authoringMode"] == "validated-direct-svg"
    assert "sceneGraphSha256" not in page
    png_path = project / page["pngKey"]
    assert png_path.is_file()
    with Image.open(png_path) as image:
        assert image.size == (1280, 720)
        assert image.convert("RGB").getpixel((200, 150)) == (225, 29, 72)


def test_direct_svg_renderer_binds_linux_cjk_font_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from instant_ppt_worker import visual_review_runtime

    svg_path = tmp_path / "slide.svg"
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
        '<text x="40" y="80" font-family="Microsoft YaHei, Arial, sans-serif">'
        "中文内容"
        "</text></svg>",
        encoding="utf-8",
    )
    target = tmp_path / "slide.png"
    observed: dict[str, object] = {}
    stream = io.BytesIO()
    Image.new("RGB", (1280, 720), "white").save(stream, format="PNG")

    noto_paths = {
        visual_review_runtime._NOTO_SANS_REGULAR,
        visual_review_runtime._NOTO_SANS_BOLD,
        visual_review_runtime._NOTO_SERIF_REGULAR,
    }
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: path in noto_paths or original_is_file(path),
    )

    def fake_svg_to_bytes(**kwargs: object) -> bytes:
        observed.update(kwargs)
        return stream.getvalue()

    monkeypatch.setattr(visual_review_runtime.resvg_py, "svg_to_bytes", fake_svg_to_bytes)

    visual_review_runtime._render_svg(svg_path, target)

    assert observed["sans_serif_family"] == "Noto Sans CJK SC"
    assert observed["serif_family"] == "Noto Serif CJK SC"
    assert observed["font_dirs"] == [str(visual_review_runtime._NOTO_FONT_ROOT)]
    assert observed["font_files"] == [
        str(visual_review_runtime._NOTO_SANS_REGULAR),
        str(visual_review_runtime._NOTO_SANS_BOLD),
        str(visual_review_runtime._NOTO_SERIF_REGULAR),
    ]


def test_model_facing_visual_review_schema_only_requests_subjective_findings() -> None:
    schema = VisualReviewModelResult.model_json_schema(by_alias=True)

    assert set(schema["properties"]) == {"issues"}
    finding = schema["$defs"]["VisualReviewModelFinding"]
    assert set(finding["properties"]) == {
        "category",
        "severity",
        "pnn",
        "message",
        "region",
            "suggestedAction",
            "targetElementIds",
    }
    for runtime_owned in (
        "workflowRunId",
        "reviewRound",
        "subjectSha256",
        "renderSetSha256",
        "contactSheetSha256",
        "issueId",
        "owner",
        "passed",
    ):
        assert runtime_owned not in json.dumps(schema)


def test_runtime_materializes_provenance_ids_ownership_and_pass_state() -> None:
    model_result = VisualReviewModelResult.model_validate(
        {
            "issues": [
                {
                    "category": "hierarchy",
                    "severity": "blocking",
                    "pnn": "P01",
                    "message": "The title and body have equal visual weight.",
                    "region": "title/body",
                    "suggestedAction": "Increase title emphasis.",
                },
                {
                    "category": "deck-consistency",
                    "severity": "advisory",
                    "pnn": None,
                    "message": "Section spacing varies across the deck.",
                    "region": "whole deck",
                    "suggestedAction": "Use one section spacing rhythm.",
                },
            ]
        }
    )

    report = _materialize_batch_report(
        model_result,
        context={
            "workflowRunId": WORKFLOW_RUN_ID,
            "reviewRound": 1,
            "subjectSha256": HASH,
            "renderSetSha256": HASH,
            "contactSheetSha256": HASH,
        },
        batch_roster=["P01", "P02"],
    )

    assert report.passed is False
    assert [issue.issue_id for issue in report.issues] == ["VR001", "VR002"]
    assert [issue.owner for issue in report.issues] == ["executor", "strategist"]
    assert [issue.scope for issue in report.issues] == ["page", "deck"]
    assert report.workflow_run_id == WORKFLOW_RUN_ID


def test_material_delivery_advisories_are_promoted_for_adaptive_repair() -> None:
    finding = VisualReviewModelResult.model_validate(
        {
            "issues": [
                {
                    "category": "density-whitespace",
                    "severity": "advisory",
                    "pnn": "P01",
                    "message": "Excessive negative space creates an unbalanced composition.",
                    "region": "lower half",
                    "suggestedAction": "Rebalance the content block.",
                }
            ]
        }
    ).issues[0]

    assert effective_visual_severity(finding) == "blocking"
    report = _materialize_batch_report(
        VisualReviewModelResult(issues=[finding]),
        context={
            "workflowRunId": WORKFLOW_RUN_ID,
            "reviewRound": 1,
            "subjectSha256": HASH,
            "renderSetSha256": HASH,
            "contactSheetSha256": HASH,
        },
        batch_roster=["P01"],
    )
    assert report.passed is False
    assert report.issues[0].severity == "blocking"


def test_v3_soft_findings_are_never_promoted_by_category_or_wording() -> None:
    finding = VisualReviewModelResult.model_validate(
        {
            "issues": [
                {
                    "category": "deck-consistency",
                    "severity": "advisory",
                    "pnn": None,
                    "message": "Inconsistent footer rhythm across the deck.",
                    "region": "whole deck",
                    "suggestedAction": "Align the footer rhythm.",
                }
            ]
        }
    ).issues[0]

    assert (
        effective_visual_severity(
            finding, policy_version="visual-review-opt-in@v3"
        )
        == "advisory"
    )


def test_v3_auto_fix_requires_page_hard_and_stable_target_ids() -> None:
    model_result = VisualReviewModelResult.model_validate(
        {
            "issues": [
                {
                    "category": "alignment-rhythm-balance",
                    "severity": "blocking",
                    "pnn": "P01",
                    "message": "Text overlaps the footer and is clipped.",
                    "region": "bottom footer",
                    "suggestedAction": "Move the text upward.",
                    "targetElementIds": ["footer-copy"],
                }
            ]
        }
    )

    report = _materialize_batch_report(
        model_result,
        context={
            "workflowRunId": WORKFLOW_RUN_ID,
            "reviewRound": 1,
            "subjectSha256": HASH,
            "renderSetSha256": HASH,
            "contactSheetSha256": HASH,
            "visualReviewPolicyVersion": "visual-review-opt-in@v3",
        },
        batch_roster=["P01"],
    )

    assert report.issues[0].severity == "blocking"
    assert report.issues[0].auto_fix_eligible is True
    assert report.issues[0].target_element_ids == ["footer-copy"]


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
        "fingerprint": FINGERPRINT,
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


def test_batched_visual_review_deduplicates_findings_and_reassigns_ids() -> None:
    blocking = {
        "issueId": "VR01",
        "fingerprint": FINGERPRINT,
        "category": "hierarchy",
        "severity": "blocking",
        "scope": "page",
        "pnn": "P01",
        "owner": "executor",
        "message": "The title and body have equal visual weight.",
        "region": "P01 title/body",
        "suggestedAction": "Increase title emphasis without changing copy.",
    }
    duplicate = {**blocking, "issueId": "VR77"}
    reports = [
        VisualReviewReport.model_validate(
            _report(passed=False, issues=[blocking])
        ),
        VisualReviewReport.model_validate(
            _report(passed=False, issues=[duplicate])
        ),
    ]

    merged = _merge_visual_review_reports(
        reports,
        context={
            "workflowRunId": WORKFLOW_RUN_ID,
            "reviewRound": 1,
            "subjectSha256": HASH,
            "renderSetSha256": HASH,
            "contactSheetSha256": HASH,
        },
    )

    assert merged.passed is False
    assert len(merged.issues) == 1
    assert merged.issues[0].issue_id == "VR001"


def test_deck_blocking_finding_expands_to_the_exact_roster() -> None:
    issue = {
        "issueId": "VR02",
        "fingerprint": FINGERPRINT,
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
    assert all(values[0]["issueId"] == issue["issueId"] for values in grouped.values())


def test_adaptive_review_passes_immediately_and_hard_stops_on_round_five() -> None:
    roster = ["P01", "P02"]
    passed = visual_review_metrics(_report(passed=True, issues=[]), roster)
    assert adaptive_visual_review_decision(
        review_round=1,
        max_rounds=5,
        metrics_history=[],
        current_metrics=passed,
    )["decision"] == "pass"

    blocking = visual_review_metrics(
        _report(
            passed=False,
            issues=[
                {
                    "issueId": "VR01",
                    "fingerprint": FINGERPRINT,
                    "category": "hierarchy",
                    "severity": "blocking",
                    "scope": "page",
                    "pnn": "P01",
                    "owner": "executor",
                    "message": "Hierarchy remains unclear.",
                    "region": "title/body",
                    "suggestedAction": "Increase contrast.",
                }
            ],
        ),
        roster,
    )
    decision = adaptive_visual_review_decision(
        review_round=5,
        max_rounds=5,
        metrics_history=[blocking, blocking, blocking, blocking],
        current_metrics=blocking,
    )
    assert decision["decision"] == "needs-manual"
    assert decision["reason"] == "max-rounds"


def test_adaptive_review_detects_two_stagnant_rounds_and_regression() -> None:
    better = {
        "blockingCount": 1,
        "affectedPageCount": 1,
        "advisoryCount": 0,
        "score": 10100,
        "qualityKey": [1, 1, 0],
        "blockingFingerprints": [FINGERPRINT],
    }
    same = dict(better)
    stalled = adaptive_visual_review_decision(
        review_round=3,
        max_rounds=5,
        metrics_history=[better, same],
        current_metrics=same,
    )
    assert stalled["decision"] == "needs-manual"
    assert stalled["reason"] == "stalled-two-rounds"

    worse = {**better, "blockingCount": 2, "score": 20100, "qualityKey": [2, 1, 0]}
    regressed = adaptive_visual_review_decision(
        review_round=2,
        max_rounds=5,
        metrics_history=[better],
        current_metrics=worse,
    )
    assert regressed["decision"] == "rollback-needs-manual"
    assert regressed["bestRound"] == 1


def test_materialized_visual_review_schema_matches_runtime_contract() -> None:
    path = Path("services/worker/contracts/visual-review.v1.schema.json")
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    generated = VisualReviewReport.model_json_schema()
    for key in ("$defs", "properties", "required", "title", "type"):
        assert on_disk[key] == generated[key]
