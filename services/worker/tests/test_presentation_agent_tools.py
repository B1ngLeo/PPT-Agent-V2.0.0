import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from instant_ppt_worker.agentic_workflow import (
    _build_deck,
    _design_spec,
    _spec_lock,
)
from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.design_spec_contract import (
    PPT_MASTER_AUTHORITY_POLICY,
    validate_design_spec,
)
from instant_ppt_worker.image_resources import empty_image_preparation
from instant_ppt_worker.ppt_master_references import (
    EXECUTOR_BASE_REFERENCES,
    executor_reference_paths,
)
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


def _upstream_context(
    tmp_path: Path,
    *,
    stage: str = "executor",
    allowed_tools: frozenset[str] | None = None,
) -> PresentationToolContext:
    legacy = _context(tmp_path, allowed_tools=allowed_tools)
    request = legacy.request.model_copy(
        update={
            "authoring": legacy.request.authoring.model_copy(
                update={"policy_version": PPT_MASTER_AUTHORITY_POLICY}
            )
        }
    )
    design_spec = (legacy.project / "design_spec.md").read_text(encoding="utf-8")
    for page in request.outline:
        design_spec = design_spec.replace(
            f"#### Slide {page.order:02d} / {page.pnn} - {page.title}",
            f"#### Slide {page.order:02d} - {page.title}",
        )
    (legacy.project / "design_spec.md").write_text(design_spec, encoding="utf-8")
    return replace(legacy, request=request, stage=stage)


def test_upstream_design_spec_uses_native_headings_without_pnn_or_exact_title(
    tmp_path: Path,
) -> None:
    request = WorkflowRequestV2.model_validate(_payload())
    _, plan = _build_deck(request, _fragments(request))
    text = _design_spec(request, plan, empty_image_preparation(tmp_path / "project"))
    for page in request.outline:
        text = text.replace(
            f"#### Slide {page.order:02d} / {page.pnn} - {page.title}",
            f"#### Slide {page.order:02d} - Refined {page.order}",
        )

    assert validate_design_spec(
        text, request.outline, upstream_authority=True
    ) == []
    assert " / P01 - " not in text


def test_upstream_svg_boundary_allows_native_semantics_without_local_title_contract(
    tmp_path: Path,
) -> None:
    context = _upstream_context(
        tmp_path, allowed_tools=frozenset({"write_or_patch_slide_svg"})
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
        '<defs><symbol id="glyph"><circle cx="5" cy="5" r="5"/>'
        '</symbol></defs><use id="brand-glyph" href="#glyph" x="40" y="40"/>'
        '<text id="headline" x="72" y="120" font-size="32">Refined page name</text>'
        '<a id="source-link" href="https://example.com/source"><text x="72" y="180">'
        "Source</text></a></svg>"
    )

    record = PresentationAgentToolRegistry(context).execute(
        tool_call_id=_call_id("upstream-boundary"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P01", "mode": "direct-svg", "svg": svg},
        input_sha256="a" * 64,
    )

    assert record["observation"]["pnn"] == "P01"
    assert "P01" not in svg
    assert 'data-pptx-role="title"' not in svg


def test_ppt_master_reference_tool_is_allowlisted_complete_and_hash_bound(
    tmp_path: Path,
) -> None:
    context = _upstream_context(
        tmp_path, allowed_tools=frozenset({"read_ppt_master_reference"})
    )
    registry = PresentationAgentToolRegistry(context)

    record = registry.execute(
        tool_call_id=_call_id("read-upstream-reference"),
        tool_name="read_ppt_master_reference",
        arguments={"path": EXECUTOR_BASE_REFERENCES[0]},
        input_sha256="b" * 64,
    )

    observation = record["observation"]
    assert observation["path"] == EXECUTOR_BASE_REFERENCES[0]
    assert observation["version"]["engine"] == "ppt-master@v4.7.0"
    assert hashlib.sha256(observation["content"].encode()).hexdigest() == observation["sha256"]
    with pytest.raises(ToolPolicyError, match="allowlist"):
        registry.execute(
            tool_call_id=_call_id("read-upstream-traversal"),
            tool_name="read_ppt_master_reference",
            arguments={"path": "../../.env"},
            input_sha256="b" * 64,
        )


def test_structured_lock_triggers_upstream_master_layout_references() -> None:
    paths = executor_reference_paths(
        "## pptx_structure\n- mode: structured\n"
        "- template_reuse_scope: layout\n- template_adherence: adaptive\n"
    )

    assert "references/executor-structured.md" in paths
    assert "references/executor-structure.md" in paths
    assert "references/pptx-structure-interface.md" in paths


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
    contract = registry.execute(
        tool_call_id=_call_id("read-design-spec-contract"),
        tool_name="read_design_spec_contract",
        arguments={},
        input_sha256="e" * 64,
    )["observation"]

    assert {item["fragmentId"] for item in approved["fragments"]} == {"fragment-1"}
    assert all(item["taint"] == "untrusted-source-data" for item in approved["fragments"])
    assert approved["approvedSnapshotSha256"] == context.request.approval.snapshot_sha256
    assert catalog["primitives"][-2:] == ["native-chart", "native-table"]
    assert "shell" not in json.dumps(catalog).casefold()
    assert contract["sourceSchemaId"] == "ppt-master://schemas/design-spec/v1"
    assert contract["canonicalSectionHeadings"][4] == "V. Layout Principles"
    assert contract["canonicalSectionHeadings"][-1] == "X. Speaker Notes Requirements"
    assert [item["pnn"] for item in contract["approvedRoster"]] == [
        page.pnn for page in context.request.outline
    ]
    assert "Keep headings, subsection headings" in contract["authoringReference"]
    assert "## V. Layout Principles" in contract["authoringReference"]


def test_design_spec_validation_reports_all_structural_and_roster_errors(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    valid = (context.project / "design_spec.md").read_text(encoding="utf-8")
    invalid = (
        valid.replace("## V. Layout Principles", "## V. 布局原则")
        .replace("- **Audience move**:", "- **受众变化**:", 1)
        .replace(
            f"| Page Count | {len(context.request.outline)} |",
            "| Page Count | 9 |",
        )
    )

    errors = validate_design_spec(invalid, context.request.outline)
    codes = {error["code"] for error in errors}

    assert "missing_section" in codes
    assert "page_count_mismatch" in codes
    assert "slide_field_missing" in codes
    assert len(errors) >= 3


def test_design_spec_policy_denial_preserves_rejected_content_and_structured_errors(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        allowed_tools=frozenset({"write_planning_artifact"}),
    )
    valid = (context.project / "design_spec.md").read_text(encoding="utf-8")
    invalid = valid.replace("## V. Layout Principles", "## V. 布局原则")
    registry = PresentationAgentToolRegistry(context)

    with pytest.raises(ToolPolicyError) as raised:
        registry.execute(
            tool_call_id=_call_id("invalid-design-spec"),
            tool_name="write_planning_artifact",
            arguments={"filename": "design_spec.md", "content": invalid},
            input_sha256="a" * 64,
        )

    assert raised.value.code == "DESIGN_SPEC_SCHEMA_INVALID"
    assert any(
        error["location"] == "layout_principles"
        for error in raised.value.details["errors"]
    )
    rejected = list((context.project / "agent" / "rejected-design-spec").glob("*.md"))
    assert len(rejected) == 1
    assert "## V. 布局原则" in rejected[0].read_text(encoding="utf-8")


def test_design_spec_ai_resource_requires_ai_image_strategy(tmp_path: Path) -> None:
    context = _context(tmp_path)
    valid = (context.project / "design_spec.md").read_text(encoding="utf-8")
    invalid = valid.replace(
        "## IX. Content Outline",
        "| hero.png | 1024×1024 | 1:1 | hero | Illustration | focal | adaptive | "
        "ai | Pending | prompt | none | hero_page |\n\n## IX. Content Outline",
    )

    errors = validate_design_spec(invalid, context.request.outline)

    assert any(error["code"] == "conditional_subheading_missing" for error in errors)


def test_design_spec_rejects_placeholder_image_resource_row(tmp_path: Path) -> None:
    context = _context(tmp_path)
    valid = (context.project / "design_spec.md").read_text(encoding="utf-8")
    invalid = valid.replace(
        "## IX. Content Outline",
        "| — | — | — | — | — | — | — | none | — | — | — | — |\n\n"
        "## IX. Content Outline",
    )

    errors = validate_design_spec(invalid, context.request.outline)

    assert any(error["code"] == "image_resource_placeholder_row" for error in errors)


def test_design_spec_rejects_invalid_image_crop_and_acquisition(tmp_path: Path) -> None:
    context = _context(tmp_path)
    valid = (context.project / "design_spec.md").read_text(encoding="utf-8")
    invalid = valid.replace(
        "## IX. Content Outline",
        "| hero.png | 1024×1024 | 1:1 | hero | Illustration | focal subject | "
        "center-crop | none | Sourced | source | avoid text | hero_page |\n\n"
        "## IX. Content Outline",
    )

    codes = {
        error["code"] for error in validate_design_spec(invalid, context.request.outline)
    }

    assert "image_resource_crop_policy_invalid" in codes
    assert "image_resource_acquire_via_invalid" in codes


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


def test_explicit_page_title_ignores_component_title_like_ids(tmp_path: Path) -> None:
    context = _context(tmp_path)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
        'data-pptx-page-role="cover">'
        f'<text id="title" x="72" y="100" font-size="64">'
        f"{context.request.outline[0].title}</text>"
        '<text id="title-sub" x="72" y="180" font-size="28">Executive summary</text>'
        '<text id="avail-title" x="72" y="240" font-size="22">Global availability</text>'
        '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
        "</svg>"
    )

    record = PresentationAgentToolRegistry(context).execute(
        tool_call_id=_call_id("component-title-like-ids"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P01", "mode": "direct-svg", "svg": svg},
        input_sha256="5" * 64,
    )

    assert record["status"] == "succeeded"


def test_direct_svg_rejects_multiple_explicit_page_title_markers(tmp_path: Path) -> None:
    context = _context(tmp_path)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
        'data-pptx-page-role="cover">'
        f'<text id="title" x="72" y="100" font-size="64">'
        f"{context.request.outline[0].title}</text>"
        '<text id="subtitle" data-pptx-role="title" x="72" y="180" font-size="64">'
        'Duplicate title marker</text>'
        '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
        "</svg>"
    )

    with pytest.raises(ToolPolicyError, match="exactly one stable title text element"):
        PresentationAgentToolRegistry(context).execute(
            tool_call_id=_call_id("multiple-explicit-title-markers"),
            tool_name="write_or_patch_slide_svg",
            arguments={"pnn": "P01", "mode": "direct-svg", "svg": svg},
            input_sha256="4" * 64,
        )


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


def test_v3_visual_repair_is_hash_bound_and_attribute_limited(tmp_path: Path) -> None:
    context = _context(tmp_path)
    request_payload = context.request.model_dump(by_alias=True, mode="json")
    request_payload["authoring"].update(
        {
            "visualReviewPolicyVersion": "visual-review-opt-in@v3",
            "visualReviewRequired": True,
            "visualReviewLevel": "standard",
            "visualReviewMaxRounds": 1,
            "authoringModel": "fake-agent@v1",
            "visualReviewModel": "fake-agent@v1",
        }
    )
    request_payload["production"]["visualReview"] = True
    request_payload["runtime"]["allowSubagentReview"] = True
    authoring_context = replace(
        context,
        request=WorkflowRequestV2.model_validate(request_payload),
    )
    title = authoring_context.request.outline[0].title
    original_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720" data-pptx-page-role="cover">'
        f'<text id="page-title" x="72" y="96" font-size="64">{title}</text>'
        '<text id="body-copy" x="72" y="220" font-size="24">Approved copy</text>'
        '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
        "</svg>"
    )
    first = PresentationAgentToolRegistry(authoring_context).execute(
        tool_call_id=_call_id("v3-visual-original"),
        tool_name="write_or_patch_slide_svg",
        arguments={"pnn": "P01", "mode": "direct-svg", "svg": original_svg},
        input_sha256="1" * 64,
    )
    repair_context = replace(
        authoring_context,
        stage="visual-repair",
        author_attempt=2,
        required_authoring_mode="direct-svg",
        visual_repair_target_ids=("body-copy",),
    )
    repaired_svg = original_svg.replace('id="body-copy" x="72"', 'id="body-copy" x="80"')
    repaired = PresentationAgentToolRegistry(repair_context).execute(
        tool_call_id=_call_id("v3-visual-repair"),
        tool_name="write_or_patch_slide_svg",
        arguments={
            "pnn": "P01",
            "mode": "direct-svg",
            "expectedBeforeSha256": first["subjectSha256"],
            "svg": repaired_svg,
        },
        input_sha256="2" * 64,
    )

    assert repaired["observation"]["visualRepair"]["changes"] == [
        {
            "elementId": "body-copy",
            "attribute": "x",
            "before": "72",
            "after": "80",
        }
    ]
    assert (
        authoring_context.project
        / repaired["observation"]["visualRepair"]["backupKey"]
    ).is_file()

    with pytest.raises(ToolPolicyError, match="presentation text"):
        PresentationAgentToolRegistry(repair_context).execute(
            tool_call_id=_call_id("v3-visual-copy-change"),
            tool_name="write_or_patch_slide_svg",
            arguments={
                "pnn": "P01",
                "mode": "direct-svg",
                "expectedBeforeSha256": repaired["subjectSha256"],
                "svg": repaired_svg.replace("Approved copy", "Changed copy"),
            },
            input_sha256="3" * 64,
        )
