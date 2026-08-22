import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from instant_ppt_worker.agentic_workflow import (
    _build_deck,
    _build_page_blueprint,
    _design_spec,
    _spec_lock,
)
from instant_ppt_worker.image_resources import empty_image_preparation
from instant_ppt_worker.presentation_agent_tools import (
    AGENT_TOOL_NAMES,
    PresentationAgentToolRegistry,
    PresentationToolContext,
    SlideSceneGraph,
    ToolCallbacks,
    ToolPolicyError,
    render_scene_graph,
)
from instant_ppt_worker.presentation_blueprint import canonical_sha256
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
) -> PresentationToolContext:
    payload = _payload()
    payload["runtime"]["allowedTools"].extend(AGENT_TOOL_NAMES)
    request = WorkflowRequestV2.model_validate(payload)
    fragments = _fragments(request)
    blueprint = _build_page_blueprint(request, fragments)
    project = tmp_path / "project"
    project.mkdir(parents=True)
    _, plan = _build_deck(request, fragments, blueprint=blueprint)
    image_preparation = empty_image_preparation(project)
    (project / "design_spec.md").write_text(
        _design_spec(request, plan, image_preparation).rstrip() + "\n",
        encoding="utf-8",
    )
    (project / "spec_lock.md").write_text(
        _spec_lock(request, plan, image_preparation).rstrip() + "\n",
        encoding="utf-8",
    )
    return PresentationToolContext(
        project=project,
        request=request,
        blueprint=blueprint,
        blueprint_sha256=canonical_sha256(blueprint.model_dump(by_alias=True, mode="json")),
        fragments=tuple(fragments),
        allowed_tools=allowed_tools or frozenset(AGENT_TOOL_NAMES),
        current_pnn=pnn,
        stage="executor_p01" if pnn == "P01" else "executor_remaining",
        author_attempt=1,
        callbacks=callbacks or ToolCallbacks(),
    )


def _call_id(label: str) -> str:
    return deterministic_ulid(hashlib.sha256(label.encode()).hexdigest())


def test_scene_graph_renders_editable_text_shapes_image_chart_and_table(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "images").mkdir(parents=True)
    (project / "images" / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    graph = SlideSceneGraph.model_validate(
        {
            "schemaVersion": 1,
            "workflowRunId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
            "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAN",
            "pnn": "P01",
            "pageBlueprintSha256": "a" * 64,
            "authorAttempt": 1,
            "nodes": [
                {
                    "nodeId": "headline-text",
                    "kind": "text",
                    "x": 72,
                    "y": 56,
                    "width": 900,
                    "height": 80,
                    "text": "A semantic assertion",
                    "fontSize": 38,
                    "fontWeight": 700,
                },
                {
                    "nodeId": "evidence-group",
                    "kind": "group",
                    "x": 72,
                    "y": 160,
                    "width": 300,
                    "height": 180,
                    "children": [
                        {
                            "nodeId": "evidence-panel",
                            "kind": "shape",
                            "shape": "round-rect",
                            "x": 72,
                            "y": 160,
                            "width": 300,
                            "height": 180,
                        }
                    ],
                },
                {
                    "nodeId": "approved-image",
                    "kind": "image",
                    "x": 400,
                    "y": 160,
                    "width": 240,
                    "height": 180,
                    "href": "../images/hero.png",
                },
                {
                    "nodeId": "data-chart-node",
                    "kind": "chart",
                    "x": 72,
                    "y": 380,
                    "width": 500,
                    "height": 260,
                    "chart": {
                        "objectKey": "data-chart",
                        "chartType": "column",
                        "values": [
                            {"label": "Sol", "value": 418},
                            {"label": "Terra", "value": 286},
                        ],
                        "unit": "req/s",
                        "sourceText": "approved fragment",
                    },
                },
                {
                    "nodeId": "decision-table-node",
                    "kind": "table",
                    "x": 620,
                    "y": 380,
                    "width": 560,
                    "height": 260,
                    "table": {
                        "objectKey": "decision-table",
                        "columns": ["Option", "Decision"],
                        "rows": [["Pilot", "Proceed"], ["Fallback", "Hold"]],
                    },
                },
            ],
        }
    )

    svg = render_scene_graph(graph, project)

    assert "A semantic assertion" in svg
    assert 'data-pptx-replace-with="chart"' in svg
    assert 'data-pptx-replace-with="table"' in svg
    assert "../images/hero.png" in svg
    assert "chart-plot-area: object=data-chart" in svg


def test_registry_writes_only_current_page_with_hash_attempt_and_stale_evidence(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path, pnn="P02")
    page = context.blueprint.pages[1]
    chart = page.chart_spec
    assert chart is not None
    registry = PresentationAgentToolRegistry(context)
    graph = {
        "schemaVersion": 1,
        "workflowRunId": context.request.workflow_run_id,
        "slideId": page.slide_id,
        "pnn": page.pnn,
        "pageBlueprintSha256": context.blueprint_sha256,
        "authorAttempt": 1,
        "nodes": [
            {
                "nodeId": "page-title",
                "kind": "text",
                "x": 72,
                "y": 52,
                "width": 1000,
                "height": 70,
                "text": page.assertion,
                "fontSize": 38,
                "fontWeight": 700,
            },
            {
                "nodeId": "approved-chart-node",
                "kind": "chart",
                "x": 100,
                "y": 170,
                "width": 1080,
                "height": 450,
                "chart": {
                    "objectKey": chart.object_key,
                    "chartType": chart.chart_type,
                    "values": [
                        {"label": point.label, "value": point.value}
                        for point in chart.values
                    ],
                    "unit": chart.unit,
                    "sourceText": "approved immutable fragment",
                },
            },
        ],
    }

    record = registry.execute(
        tool_call_id=_call_id("write-p02"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P02", "mode": "scene-graph", "sceneGraph": graph},
        input_sha256="b" * 64,
    )
    repeated = registry.execute(
        tool_call_id=_call_id("write-p02"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P02", "mode": "scene-graph", "sceneGraph": graph},
        input_sha256="b" * 64,
    )

    svg_path = context.project / "svg_output" / "slide_02.svg"
    assert record == repeated
    assert record["authorAttempt"] == 1
    assert record["subjectSha256"] == hashlib.sha256(svg_path.read_bytes()).hexdigest()
    assert "final-svg-gate" in record["stale"]
    assert record["observation"]["authoringMode"] == "scene-graph"
    stale = json.loads(
        (context.project / "validation" / "agent-stale.json").read_text(encoding="utf-8")
    )
    assert stale["entries"][0]["toolCallId"] == record["toolCallId"]
    report_path = context.project / "validation" / "scene-graph-svg-gate.json"
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

    assert {item["fragmentId"] for item in approved["fragments"]} == set(
        context.blueprint.pages[0].evidence_refs
    )
    assert all(item["taint"] == "untrusted-source-data" for item in approved["fragments"])
    assert approved["approvedSnapshotSha256"] == context.request.approval.snapshot_sha256
    assert catalog["primitives"][-2:] == ["native-chart", "native-table"]
    assert "shell" not in json.dumps(catalog).casefold()


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
        'viewBox="0 0 1280 720">'
        '<rect id="custom-panel" x="72" y="72" width="1136" height="576" '
        'fill="#FFFFFF" stroke="#CBD5E1"/>'
        '<path id="custom-relationship" d="M 120 360 C 360 120 720 600 1120 360" '
        'fill="none" stroke="#2563EB" stroke-width="4"/>'
        '<text id="custom-title" x="96" y="128" font-size="38">Custom composition</text>'
        "</svg>"
    )

    record = registry.execute(
        tool_call_id=_call_id("direct-svg"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P01", "mode": "direct-svg", "svg": svg},
        input_sha256="9" * 64,
    )

    assert record["observation"]["authoringMode"] == "validated-direct-svg"
    assert "custom-relationship" in (
        context.project / "svg_output" / "slide_01.svg"
    ).read_text(encoding="utf-8")


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
    with pytest.raises(ToolPolicyError, match="owned JSON namespace"):
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


def test_scene_graph_rejects_invented_chart_values_and_stale_ownership(tmp_path: Path) -> None:
    context = _context(tmp_path, pnn="P02")
    page = context.blueprint.pages[1]
    chart = page.chart_spec
    assert chart is not None
    graph = {
        "schemaVersion": 1,
        "workflowRunId": context.request.workflow_run_id,
        "slideId": page.slide_id,
        "pnn": page.pnn,
        "pageBlueprintSha256": context.blueprint_sha256,
        "authorAttempt": 1,
        "nodes": [
            {
                "nodeId": "invented-chart-node",
                "kind": "chart",
                "x": 100,
                "y": 150,
                "width": 1000,
                "height": 450,
                "chart": {
                    "objectKey": chart.object_key,
                    "chartType": chart.chart_type,
                    "values": [
                        {"label": chart.values[0].label, "value": 999999},
                        {"label": chart.values[1].label, "value": chart.values[1].value},
                    ],
                    "unit": chart.unit,
                    "sourceText": "invented",
                },
            }
        ],
    }
    registry = PresentationAgentToolRegistry(context)

    with pytest.raises(ToolPolicyError, match="differs from approved Blueprint evidence"):
        registry.execute(
            tool_call_id=_call_id("invented-chart"),
            tool_name="write_or_patch_slide_svg",
            arguments={"pnn": "P02", "mode": "scene-graph", "sceneGraph": graph},
            input_sha256="1" * 64,
        )
    graph["pageBlueprintSha256"] = "0" * 64
    with pytest.raises(ToolPolicyError, match="ownership/hash/attempt"):
        registry.execute(
            tool_call_id=_call_id("stale-graph"),
            tool_name="write_or_patch_slide_svg",
            arguments={"pnn": "P02", "mode": "scene-graph", "sceneGraph": graph},
            input_sha256="1" * 64,
        )


def test_direct_svg_escape_cannot_bypass_approved_chart_evidence(tmp_path: Path) -> None:
    context = _context(tmp_path, pnn="P02")
    page = context.blueprint.pages[1]
    chart = page.chart_spec
    assert chart is not None
    metadata = json.dumps(
        {
            "name": chart.object_key,
            "x": 100,
            "y": 160,
            "width": 1000,
            "height": 450,
            "type": chart.chart_type,
            "categories": [point.label for point in chart.values],
            "series": [
                {
                    "name": chart.unit,
                    "values": [999999, *[point.value for point in chart.values[1:]]],
                }
            ],
        },
        ensure_ascii=False,
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720">'
        f'<g id="{chart.object_key}" data-pptx-replace-with="chart">'
        f'<metadata type="application/json">{metadata}</metadata>'
        '<rect id="chart-fallback" x="100" y="160" width="1000" height="450"/>'
        "</g></svg>"
    )

    with pytest.raises(ToolPolicyError, match="differs from approved Blueprint evidence"):
        PresentationAgentToolRegistry(context).execute(
            tool_call_id=_call_id("direct-invented-chart"),
            tool_name="write_or_patch_slide_svg",
            arguments={"pnn": "P02", "mode": "direct-svg", "svg": svg},
            input_sha256="2" * 64,
        )


def test_materialized_scene_graph_schema_matches_runtime_contract() -> None:
    path = Path("services/worker/contracts/slide-scene-graph.v1.schema.json")
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    generated = SlideSceneGraph.model_json_schema()
    for key in ("$defs", "properties", "required", "title", "type"):
        assert on_disk[key] == generated[key]
