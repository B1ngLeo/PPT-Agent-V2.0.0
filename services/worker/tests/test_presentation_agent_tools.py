import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from instant_ppt_worker.agentic_workflow import (
    _build_deck,
    _design_spec,
    _spec_lock,
)
from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.image_resources import empty_image_preparation
from instant_ppt_worker.presentation_agent_tools import (
    AGENT_TOOL_NAMES,
    PresentationAgentToolRegistry,
    PresentationToolContext,
    ToolCallbacks,
    ToolPolicyError,
)
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.workflow_models import WorkflowRequestV2

from .test_workflow_contracts import _payload

ROOT = Path(__file__).resolve().parents[3]


def _fragments(request: WorkflowRequestV2) -> list[dict[str, object]]:
    return [
        fragment.model_dump(by_alias=True, mode="json")
        for artifact in request.sources.artifacts
        for fragment in artifact.fragments
    ]


def _context(
    tmp_path: Path,
    *,
    pnn: str = "P01",
    allowed_tools: frozenset[str] | None = None,
    callbacks: ToolCallbacks | None = None,
    visual_review_required: bool = False,
    native_charts_enabled: bool = True,
    required_authoring_mode: str | None = None,
) -> PresentationToolContext:
    payload = _payload()
    payload["runtime"]["allowedTools"].extend(AGENT_TOOL_NAMES)
    payload["authoring"]["visualReviewRequired"] = visual_review_required
    payload["production"]["visualReview"] = visual_review_required
    payload["production"]["nativeCharts"] = native_charts_enabled
    payload["runtime"]["allowSubagentReview"] = visual_review_required
    request = WorkflowRequestV2.model_validate(payload)
    fragments = _fragments(request)
    project = tmp_path / "project"
    project.mkdir(parents=True)
    _, plan = _build_deck(request, fragments)
    image_preparation = empty_image_preparation(project)
    design_spec_path = project / "design_spec.md"
    design_spec_path.write_text(
        _design_spec(request, plan, image_preparation).rstrip() + "\n",
        encoding="utf-8",
    )
    (project / "spec_lock.md").write_text(
        _spec_lock(
            request,
            plan,
            image_preparation,
            design_spec_sha256=sha256_file(design_spec_path),
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    return PresentationToolContext(
        project=project,
        request=request,
        fragments=tuple(fragments),
        allowed_tools=allowed_tools or frozenset(AGENT_TOOL_NAMES),
        current_pnn=pnn,
        stage="executor_p01" if pnn == "P01" else "executor_remaining",
        author_attempt=1,
        callbacks=callbacks or ToolCallbacks(),
        required_authoring_mode=required_authoring_mode,
    )


def _call_id(label: str) -> str:
    return deterministic_ulid(hashlib.sha256(label.encode()).hexdigest())


def _execution_chart(context: PresentationToolContext) -> dict[str, object]:
    _, plan = _build_deck(context.request, list(context.fragments))
    chart = plan["roster"][1]["chart"]
    assert chart is not None
    return chart


def _direct_chart_svg(page: object, title: str, chart: dict[str, object]) -> str:
    values = list(chart["values"])
    metadata = json.dumps(
        {
            "name": chart["objectKey"],
            "x": 100,
            "y": 170,
            "width": 1080,
            "height": 450,
            "type": "column",
            "categories": [label for label, _ in values],
            "series": [{"name": chart["unit"], "values": [value for _, value in values]}],
        },
        ensure_ascii=False,
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720" data-pptx-page-role="data">'
        f'<text id="page-title" x="72" y="96" font-size="48">{title}</text>'
        f'<g id="{chart["objectKey"]}" data-pptx-replace-with="chart" '
        'data-pptx-bounds="100 170 1080 450">'
        f'<metadata type="application/json">{metadata}</metadata>'
        '<rect id="chart-fallback" x="100" y="170" width="1080" height="450" '
        'fill="#FFFFFF" stroke="#CBD5E1"/>'
        f'</g><text id="page-number" x="1208" y="680" text-anchor="end">{page.pnn}</text>'
        "</svg>"
    )


def test_registry_writes_only_current_page_with_hash_attempt_and_stale_evidence(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path, pnn="P02")
    page = context.request.outline[1]
    chart = _execution_chart(context)
    registry = PresentationAgentToolRegistry(context)
    svg = _direct_chart_svg(page, context.request.outline[1].title, chart)

    record = registry.execute(
        tool_call_id=_call_id("write-p02"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P02", "mode": "direct-svg", "svg": svg},
        input_sha256="b" * 64,
    )
    repeated = registry.execute(
        tool_call_id=_call_id("write-p02"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P02", "mode": "direct-svg", "svg": svg},
        input_sha256="b" * 64,
    )

    svg_path = context.project / "svg_output" / "slide_02.svg"
    assert record == repeated
    assert record["authorAttempt"] == 1
    assert record["subjectSha256"] == hashlib.sha256(svg_path.read_bytes()).hexdigest()
    assert "final-svg-gate" in record["stale"]
    assert record["observation"]["authoringMode"] == "validated-direct-svg"
    stale = json.loads(
        (context.project / "validation" / "agent-stale.json").read_text(encoding="utf-8")
    )
    assert stale["entries"][0]["toolCallId"] == record["toolCallId"]
    report_path = context.project / "validation" / "direct-svg-gate.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "vendor/ppt-master/scripts/svg_quality_checker.py"),
            str(context.project),
            "--format",
            "ppt169",
            "--stage",
            "final",
            "--json-output",
            str(report_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    gate_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert gate_report["categories"]["blocking"]["count"] == 0


def test_registry_returns_only_current_approved_context_and_closed_catalog(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    registry = PresentationAgentToolRegistry(context)

    approved = registry.execute(
        tool_call_id=_call_id("read-context"),
        tool_name="read_approved_context",
        arguments={"pnn": "P01"},
        input_sha256="c" * 64,
    )["observation"]
    catalog = registry.execute(
        tool_call_id=_call_id("read-catalog"),
        tool_name="read_design_catalog",
        arguments={},
        input_sha256="d" * 64,
    )["observation"]

    assert {item["fragmentId"] for item in approved["fragments"]} == {"fragment-1"}
    assert all(item["taint"] == "untrusted-source-data" for item in approved["fragments"])
    assert approved["approvedSnapshotSha256"] == context.request.approval.snapshot_sha256
    assert catalog["primitives"][-2:] == ["native-chart", "native-table"]
    assert "shell" not in json.dumps(catalog).casefold()


def test_registry_hides_native_chart_primitive_when_feature_is_disabled(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path, native_charts_enabled=False)
    registry = PresentationAgentToolRegistry(context)

    catalog = registry.execute(
        tool_call_id=_call_id("read-catalog-without-charts"),
        tool_name="read_design_catalog",
        arguments={},
        input_sha256="d" * 64,
    )["observation"]

    assert "native-chart" not in catalog["primitives"]
    assert "native-table" in catalog["primitives"]


def test_registry_gate_observation_is_hash_bound_and_enters_tool_evidence(
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, str]] = []

    def gate(pnn: str, _path: Path, subject_sha256: str) -> dict[str, object]:
        seen.append((pnn, subject_sha256))
        return {"passed": False, "findings": [{"code": "TITLE_TOO_SMALL"}]}

    context = _context(tmp_path, callbacks=ToolCallbacks(svg_gate=gate))
    svg_path = context.project / "svg_output" / "slide_01.svg"
    svg_path.parent.mkdir(parents=True)
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720"><text id="page-title" x="72" y="100">Title</text></svg>\n',
        encoding="utf-8",
    )
    registry = PresentationAgentToolRegistry(context)

    record = registry.execute(
        tool_call_id=_call_id("run-gate"),
        tool_name="run_svg_gate",
        arguments={"pnn": "P01"},
        input_sha256="e" * 64,
    )

    assert seen == [("P01", hashlib.sha256(svg_path.read_bytes()).hexdigest())]
    assert record["observation"]["report"]["passed"] is False
    assert record["observation"]["report"]["findings"][0]["code"] == "TITLE_TOO_SMALL"


def test_valid_direct_svg_escape_hatch_is_sanitized_and_hash_bound(tmp_path: Path) -> None:
    context = _context(tmp_path)
    registry = PresentationAgentToolRegistry(context)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720" data-pptx-page-role="cover">'
        '<rect id="custom-panel" x="72" y="72" width="1136" height="576" '
        'fill="#FFFFFF" stroke="#CBD5E1"/>'
        '<path id="custom-relationship" d="M 120 360 C 360 120 720 600 1120 360" '
        'fill="none" stroke="#2563EB" stroke-width="4"/>'
        f'<text id="custom-title" x="96" y="128" font-size="64">'
        f"{context.request.outline[0].title}</text>"
        '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
        "</svg>"
    )

    record = registry.execute(
        tool_call_id=_call_id("direct-svg"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P01", "mode": "direct-svg", "svg": svg},
        input_sha256="9" * 64,
    )

    assert record["observation"]["authoringMode"] == "validated-direct-svg"
    assert "custom-relationship" in (context.project / "svg_output" / "slide_01.svg").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("mode", ["Direct SVG", "DirectSVG", "direct_svg", " direct-svg ", None])
def test_direct_svg_mode_provider_spelling_variants_are_canonicalized(
    tmp_path: Path,
    mode: str | None,
) -> None:
    context = _context(tmp_path)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
        'data-pptx-page-role="cover">'
        f'<text id="page-title" x="72" y="100" font-size="64">'
        f"{context.request.outline[0].title}</text>"
        '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
        "</svg>"
    )

    record = PresentationAgentToolRegistry(context).execute(
        tool_call_id=_call_id(mode or "missing-mode"),
        tool_name="write_or_patch_slide_svg",
        arguments={
            "pnn": "P01",
            **({"mode": mode} if mode is not None else {}),
            "svg": svg,
        },
        input_sha256="6" * 64,
    )

    assert record["observation"]["authoringMode"] == "validated-direct-svg"


@pytest.mark.parametrize("title_id", ["title-p01", "p01-title"])
def test_stable_title_id_prefix_and_suffix_variants_are_accepted(
    tmp_path: Path,
    title_id: str,
) -> None:
    context = _context(tmp_path)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
        'data-pptx-page-role="cover">'
        f'<text id="{title_id}" x="72" y="100" font-size="64">'
        f"{context.request.outline[0].title}</text>"
        f'<text id="body-copy" x="72" y="220" font-size="28">'
        f"围绕“{context.request.outline[0].title}”展开解读</text>"
        '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
        "</svg>"
    )

    record = PresentationAgentToolRegistry(context).execute(
        tool_call_id=_call_id(title_id),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P01", "mode": "direct-svg", "svg": svg},
        input_sha256="5" * 64,
    )

    assert record["status"] == "succeeded"


def test_visual_review_allows_direct_svg_authoring(tmp_path: Path) -> None:
    context = _context(tmp_path, visual_review_required=True)

    record = PresentationAgentToolRegistry(context).execute(
        tool_call_id=_call_id("review-direct-svg"),
        tool_name="write_or_patch_slide_svg",
        arguments={
            "pnn": "P01",
            "mode": "direct-svg",
            "svg": (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
                'data-pptx-page-role="cover">'
                f'<text id="page-title" x="72" y="100" font-size="64">'
                f"{context.request.outline[0].title}</text>"
                '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
                "</svg>"
            ),
        },
        input_sha256="8" * 64,
    )

    assert record["observation"]["authoringMode"] == "validated-direct-svg"
    assert (context.project / "svg_output" / "slide_01.svg").is_file()
    assert "sceneGraphKey" not in record["observation"]


def test_repair_context_preserves_the_current_page_authoring_mode(tmp_path: Path) -> None:
    context = _context(
        tmp_path,
        visual_review_required=True,
        required_authoring_mode="direct-svg",
    )

    with pytest.raises(ToolPolicyError, match="must be direct-svg"):
        PresentationAgentToolRegistry(context).execute(
            tool_call_id=_call_id("repair-mode-switch"),
            tool_name="write_or_patch_slide_svg",
            arguments={
                "pnn": "P01",
                "mode": "legacy-mode",
            },
            input_sha256="7" * 64,
        )


def test_registry_rejects_cross_page_arbitrary_path_active_svg_and_unallowed_tool(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        allowed_tools=frozenset({"write_or_patch_slide_svg", "write_planning_artifact"}),
    )
    registry = PresentationAgentToolRegistry(context)

    with pytest.raises(ToolPolicyError, match="current approved PNN"):
        registry.execute(
            tool_call_id=_call_id("cross-page"),
            tool_name="write_or_patch_slide_svg",
            arguments={"pnn": "P02", "mode": "direct-svg", "svg": "<svg/>"},
            input_sha256="f" * 64,
        )
    with pytest.raises(ToolPolicyError, match="only the canonical design_spec.md"):
        registry.execute(
            tool_call_id=_call_id("path-traversal"),
            tool_name="write_planning_artifact",
            arguments={"filename": "../../approval.json", "payload": {}},
            input_sha256="f" * 64,
        )
    with pytest.raises(ToolPolicyError, match="forbidden active"):
        registry.execute(
            tool_call_id=_call_id("active-svg"),
            tool_name="write_or_patch_slide_svg",
            arguments={
                "pnn": "P01",
                "mode": "direct-svg",
                "svg": (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
                    'viewBox="0 0 1280 720"><script id="active-script">alert(1)</script></svg>'
                ),
            },
            input_sha256="f" * 64,
        )
    with pytest.raises(ToolPolicyError, match="not allowed"):
        registry.execute(
            tool_call_id=_call_id("review-not-allowed"),
            tool_name="request_visual_review",
            arguments={},
            input_sha256="f" * 64,
        )


def test_direct_svg_escape_cannot_bypass_approved_chart_evidence(tmp_path: Path) -> None:
    context = _context(tmp_path, pnn="P02")
    chart = _execution_chart(context)
    values = list(chart["values"])
    metadata = json.dumps(
        {
            "name": chart["objectKey"],
            "x": 100,
            "y": 160,
            "width": 1000,
            "height": 450,
            "type": "column",
            "categories": [label for label, _ in values],
            "series": [
                {
                    "name": chart["unit"],
                    "values": [999999, *[value for _, value in values[1:]]],
                }
            ],
        },
        ensure_ascii=False,
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720" data-pptx-page-role="data">'
        f'<text id="page-title" x="72" y="96" font-size="48">'
        f"{context.request.outline[1].title}</text>"
        f'<g id="{chart["objectKey"]}" data-pptx-replace-with="chart">'
        f'<metadata type="application/json">{metadata}</metadata>'
        '<rect id="chart-fallback" x="100" y="160" width="1000" height="450"/>'
        '</g><text id="page-number" x="1208" y="680" text-anchor="end">P02</text>'
        "</svg>"
    )

    with pytest.raises(ToolPolicyError, match="numeric values lack approved source support"):
        PresentationAgentToolRegistry(context).execute(
            tool_call_id=_call_id("direct-invented-chart"),
            tool_name="write_or_patch_slide_svg",
            arguments={"pnn": "P02", "mode": "direct-svg", "svg": svg},
            input_sha256="2" * 64,
        )
