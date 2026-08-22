import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import instant_ppt_worker.agentic_workflow as workflow_module
import pytest
from instant_ppt_worker.adapter import run_request
from instant_ppt_worker.errors import CONTENT_QA_FAILED, AdapterError
from instant_ppt_worker.presentation_agent_fixture_provider import (
    DeterministicPresentationAgentProvider,
)
from instant_ppt_worker.presentation_blueprint import (
    canonical_sha256,
    validate_page_blueprint,
)
from instant_ppt_worker.providers import TextCompletion
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.visual_review_runtime import VisualReviewReport
from instant_ppt_worker.workflow_models import WorkflowRequestV2

from .test_workflow_contracts import _payload

ROOT = Path(__file__).resolve().parents[3]


def test_nested_workflow_tools_use_a_stable_python_hash_seed() -> None:
    assert workflow_module._safe_environment()["PYTHONHASHSEED"] == "0"


def test_gate_failure_prefers_first_structured_blocking_finding(tmp_path: Path) -> None:
    report_path = tmp_path / "quality-report.json"
    report_path.write_text(
        json.dumps(
            {
                "categories": {
                    "blocking": {
                        "issues": [
                            {
                                "file": "slide_01.svg",
                                "message": "cover-message exceeds the root viewBox",
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    message = workflow_module._blocking_report_message(
        ["python", "checker.py", "--json-output", str(report_path)]
    )

    assert message == "cover-message exceeds the root viewBox"


def test_conflicting_approved_chart_facts_are_blocking() -> None:
    fragments = [
        {"text": "Sol: 418 req/s, Sol: 999 req/s"},
    ]
    with pytest.raises(AdapterError) as captured:
        workflow_module._chart_values(fragments)
    assert captured.value.code == CONTENT_QA_FAILED


def test_same_label_in_distinct_benchmarks_is_not_a_false_conflict() -> None:
    fragments = [
        {"text": "ExploitBench：Sol 73.5%，GPT-5.5 47.9%"},
        {"text": "SEC-Bench Pro：Sol 71.2%，GPT-5.5 45.8%"},
    ]

    values, unit = workflow_module._chart_values(fragments)

    assert values == [("Sol", 73.5), ("GPT-5.5", 47.9)]
    assert unit == "%"


def test_chinese_labeled_values_form_a_sourced_chart_series() -> None:
    fragments = [{"text": "方案甲为 73.5%，方案乙达到 47.9%。"}]

    values, unit = workflow_module._chart_values(fragments)

    assert values == [("方案甲", 73.5), ("方案乙", 47.9)]
    assert unit == "%"


def test_markdown_table_binds_headers_to_values_and_ignores_incomplete_rows() -> None:
    table = "\n".join(
        [
            "| 评测 | Sol | Sol Ultra | Terra | GPT-5.5 |",
            "| --- | ---: | ---: | ---: | ---: |",
            "| Terminal-Bench 2.1 | 88.8% | 91.9% | 87.4% | 85.6% |",
            "| 仅单值 | 80% | — | — | — |",
            "",
            "| 不是合法表格 | Sol | Terra |",
            "| no separator | 90% | 80% |",
        ]
    )

    series = workflow_module._chart_series([{"text": table, "kind": "table"}])

    assert series == [
        {
            "context": "Terminal-Bench 2.1",
            "values": [
                ("Sol", 88.8),
                ("Sol Ultra", 91.9),
                ("Terra", 87.4),
                ("GPT-5.5", 85.6),
            ],
            "unit": "%",
        }
    ]


def test_conflicting_duplicate_markdown_table_headers_are_blocking() -> None:
    table = "\n".join(
        [
            "| 评测 | Sol | Sol | Terra |",
            "| --- | --- | --- | --- |",
            "| BrowseComp | 92.2% | 99.9% | 87.5% |",
        ]
    )

    with pytest.raises(AdapterError) as captured:
        workflow_module._chart_series([{"text": table, "kind": "table"}])

    assert captured.value.code == CONTENT_QA_FAILED


def test_sentences_preserve_model_versions_decimals_and_skip_headings() -> None:
    fragments = [
        {"fragmentId": "heading-1", "kind": "heading", "text": "## 效率默认与最高能力"},
        {
            "fragmentId": "processing-note",
            "kind": "paragraph",
            "text": "本文件是为本地安全测试制作的无外部关系版本，保留核心事实。",
        },
        {
            "fragmentId": "paragraph-1",
            "kind": "paragraph",
            "text": (
                "GPT-5.6 Sol 在评测中达到 53.6，领先竞品 13.1 分。"
                "Sol max 比竞品高 2.8 分，且用时不到一半。"
            ),
        },
    ]

    sentences = [text for text, _ in workflow_module._sentences(fragments)]

    assert sentences == [
        "GPT-5.6 Sol 在评测中达到 53.6，领先竞品 13.1 分。",
        "Sol max 比竞品高 2.8 分，且用时不到一半。",
    ]
    assert all(not text.startswith(("6，", "8 分", "##")) for text in sentences)


def test_concise_title_never_reuses_polluted_outline_or_splits_decimals() -> None:
    source = (
        "Sol max 在 Artificial Analysis Coding Agent Index 上以 80 分创纪录，"
        "比 Fable 5 高 2.8 分，输出 token 和用时都不到一半。"
    )

    title = workflow_module._concise_title(source)

    assert title == "Sol max 在 Artificial Analysis Coding Agent Index 上以 80 分创纪录"
    assert not title.endswith(("2", "."))


def test_data_slides_bind_distinct_benchmark_series() -> None:
    workflow = _payload()
    base = workflow["outline"][1]
    workflow["outline"] = [
        workflow["outline"][0],
        base,
        {
            **base,
            "outlineSlideId": deterministic_ulid(hashlib.sha256(b"chart-outline-3").hexdigest()),
            "slideId": deterministic_ulid(hashlib.sha256(b"chart-slide-3").hexdigest()),
            "pnn": "P03",
            "order": 3,
        },
        {
            **base,
            "outlineSlideId": deterministic_ulid(hashlib.sha256(b"chart-outline-4").hexdigest()),
            "slideId": deterministic_ulid(hashlib.sha256(b"chart-slide-4").hexdigest()),
            "pnn": "P04",
            "order": 4,
        },
    ]
    text = (
        "Terminal-Bench 2.1：Sol 88.8%，Sol Ultra 91.9%，Terra 87.4%。\n"
        "BrowseComp：Sol 90.4%，Sol Ultra 92.2%，Terra 87.5%。\n"
        "SEC-Bench Pro：Sol 71.2%，Sol Ultra 74.3%，Terra 57.7%。"
    )
    fragment = workflow["sources"]["artifacts"][0]["fragments"][0]
    fragment.update(
        {
            "kind": "paragraph",
            "text": text,
            "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    )

    _, plan = workflow_module._build_deck(WorkflowRequestV2.model_validate(workflow), [fragment])
    charts = [item["chart"] for item in plan["roster"] if item["chart"]]

    assert [chart["context"] for chart in charts] == [
        "Terminal-Bench 2.1",
        "BrowseComp",
        "SEC-Bench Pro",
    ]
    assert len({tuple(chart["values"]) for chart in charts}) == 3
    assert [slide["title"] for slide in plan["roster"][1:]] == [
        "Terminal-Bench 2.1 中，Sol Ultra 达到 91.9%，领先 Sol 3%",
        "BrowseComp 中，Sol Ultra 达到 92.2%，领先 Sol 2%",
        "SEC-Bench Pro 中，Sol Ultra 达到 74.3%，领先 Sol 4%",
    ]


def test_real_gpt56_announcement_supplies_expected_table_chart_series(
    tmp_path: Path,
) -> None:
    source = ROOT / "tests/OpenAI_GPT-5.6_发布公告_中文版_2026-07-09.docx"
    markdown_path = tmp_path / "gpt56.md"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "vendor/ppt-master/scripts/source_to_md.py"),
            str(source),
            "-o",
            str(markdown_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    fragments = workflow_module._markdown_table_series(
        markdown_path.read_text(encoding="utf-8")
    )
    by_context = {item["context"]: item for item in fragments}

    assert by_context["Terminal-Bench 2.1"]["values"] == [
        ("Sol", 88.8),
        ("Sol Ultra", 91.9),
        ("Terra", 87.4),
        ("Luna", 84.7),
        ("GPT-5.5", 85.6),
    ]
    assert by_context["BrowseComp"]["values"][1] == ("Sol Ultra", 92.2)
    assert by_context["SEC-Bench Pro"]["values"][1] == ("Sol Ultra", 74.3)


def test_no_source_limited_draft_authors_distinct_topic_specific_copy() -> None:
    workflow = _payload()
    workflow["sources"] = {
        "mode": "no-source-limited",
        "artifacts": [],
        "manifestSha256": "b" * 64,
        "continueLimitedDraft": True,
    }
    workflow["outline"][1].update(
        {
            "role": "ending",
            "title": "试点决策与下一步",
            "audienceQuestion": "如何形成可执行的试点选择并推进？",
        }
    )

    deck, _ = workflow_module._build_deck(WorkflowRequestV2.model_validate(workflow), [])

    bodies = ["；".join(slide.body) for slide in deck.slides]
    assert len(set(bodies)) == len(bodies)
    assert all("私有模型公告解读" in body for body in bodies)
    assert all(len(body) >= 40 for body in bodies)
    assert all("请生成" not in body and "给出第" not in body for body in bodies)
    assert "结论：" in bodies[-1] and "行动：" in bodies[-1]


def test_page_blueprint_uses_semantic_evidence_instead_of_page_position() -> None:
    workflow = _payload()
    workflow["outline"][0].update(
        {
            "role": "content",
            "title": "安全审计结论",
            "audienceQuestion": "安全审计是否通过？",
        }
    )
    workflow["outline"][1].update(
        {
            "role": "content",
            "title": "性能吞吐结论",
            "audienceQuestion": "性能吞吐是否达标？",
        }
    )
    request = WorkflowRequestV2.model_validate(workflow)
    fragments = [
        {
            "fragmentId": "performance-fragment",
            "kind": "paragraph",
            "text": "性能吞吐测试稳定达到预定目标，建议进入受控试点。",
        },
        {
            "fragmentId": "security-fragment",
            "kind": "paragraph",
            "text": "安全审计已通过全部强制检查，未发现阻断问题。",
        },
    ]

    blueprint = workflow_module._build_page_blueprint(request, fragments)
    repeated = workflow_module._build_page_blueprint(request, fragments)

    assert blueprint.pages[0].evidence_refs == ["security-fragment"]
    assert blueprint.pages[1].evidence_refs == ["performance-fragment"]
    assert [(page.slide_id, page.pnn, page.order) for page in blueprint.pages] == [
        (slide.slide_id, slide.pnn, slide.order) for slide in request.outline
    ]
    assert canonical_sha256(blueprint.model_dump(by_alias=True, mode="json")) == canonical_sha256(
        repeated.model_dump(by_alias=True, mode="json")
    )
    assert validate_page_blueprint(blueprint, request, fragments)["passed"] is True


def test_page_blueprint_gate_rejects_an_unsupported_assertion() -> None:
    workflow = _payload()
    request = WorkflowRequestV2.model_validate(workflow)
    fragments = [
        fragment.model_dump(by_alias=True, mode="json")
        for artifact in request.sources.artifacts
        for fragment in artifact.fragments
    ]
    blueprint = workflow_module._build_page_blueprint(request, fragments)
    blueprint.pages[0].assertion = "未经批准的财务收益增长 99%"

    report = validate_page_blueprint(blueprint, request, fragments)

    assert report["passed"] is False
    assert any(
        finding["code"] == "BLUEPRINT_ASSERTION_UNSUPPORTED"
        for finding in report["findings"]
    )


def test_no_source_limited_vertical_slice_passes_all_release_gates(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["sources"] = {
        "mode": "no-source-limited",
        "artifacts": [],
        "manifestSha256": "b" * 64,
        "continueLimitedDraft": True,
    }
    workflow["intent"].update(
        {
            "title": "ISSUE-002 最终用户旅程：从可用内容初稿到原生可编辑演示",
            "audience": "管理层",
            "desiredOutcome": "策略决策",
        }
    )
    roles_and_titles = [
        ("cover", "封面与核心命题"),
        ("content", "一页结论"),
        ("comparison", "现状与关键数据"),
        ("timeline", "问题拆解"),
        ("risk_action", "原因与洞察"),
        ("content", "策略选择"),
        ("comparison", "行动路线图"),
        ("ending", "收束与下一步"),
    ]
    workflow["outline"] = [
        {
            "outlineSlideId": deterministic_ulid(
                hashlib.sha256(f"no-source-outline-{order}".encode()).hexdigest()
            ),
            "slideId": deterministic_ulid(
                hashlib.sha256(f"no-source-slide-{order}".encode()).hexdigest()
            ),
            "pnn": f"P{order:02d}",
            "order": order,
            "role": role,
            "title": title,
            "audienceQuestion": f"如何用“{title}”支持试点决策？",
        }
        for order, (role, title) in enumerate(roles_and_titles, start=1)
    ]
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    request = {
        "schemaVersion": 2,
        "requestId": "issue-002-no-source-limited",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/no-source",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    assert response.status == "succeeded"
    [project] = (tmp_path / "generated").glob("no-source_ppt169_*")
    deck = json.loads((project / "deck-plan.json").read_text(encoding="utf-8"))
    bodies = ["；".join(slide["body"]) for slide in deck["slides"]]
    assert len(set(bodies)) == len(bodies)
    assert all("ISSUE-002 最终用户" in body for body in bodies)


def test_default_agentic_vertical_slice_exports_native_chart(tmp_path: Path) -> None:
    workflow = _payload()
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    request = {
        "schemaVersion": 2,
        "requestId": "issue-002-stage-b",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/issue002",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    assert response.status == "succeeded"
    [project] = (tmp_path / "generated").glob("issue002_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    provider_request = json.loads(
        (project / "analysis" / "provider-request.json").read_text(encoding="utf-8")
    )
    events = (project / "validation" / "workflow-events.jsonl").read_text(encoding="utf-8")

    assert result["status"] == "succeeded"
    assert result["profile"] == "default-agentic"
    assert provider_request["fragments"][0]["text"].find("ORBIT-NONCE-8472") >= 0
    assert provider_request["fragments"][0]["sourceInstructionsIgnored"] is True
    assert '"author": "main-presentation-agent"' in events
    assert "current-main-agent" not in events
    assert "quick-generate" not in events

    evidence_map = json.loads(
        (project / "analysis" / "evidence-map.json").read_text(encoding="utf-8")
    )
    blueprint = json.loads(
        (project / "analysis" / "page-blueprint.v1.json").read_text(encoding="utf-8")
    )
    blueprint_support = json.loads(
        (project / "validation" / "page-blueprint-support.json").read_text(
            encoding="utf-8"
        )
    )
    blueprint_consistency = json.loads(
        (project / "validation" / "page-blueprint-consistency.json").read_text(
            encoding="utf-8"
        )
    )
    content_reports = {
        stage: json.loads((project / "validation" / filename).read_text(encoding="utf-8"))
        for stage, filename in {
            "design": "content-design-spec.json",
            "final": "content-final-svg.json",
            "pptx": "content-pptx.json",
        }.items()
    }
    assert all(report["passed"] for report in content_reports.values())
    blueprint_sha256 = canonical_sha256(blueprint)
    assert blueprint["authoringMode"] == "agent-strategist"
    strategist_turn = project / "agent" / "turns" / f"{blueprint['strategistTurnId']}.json"
    assert strategist_turn.is_file()
    assert blueprint_support["passed"] is True
    assert blueprint_support["blueprintSha256"] == blueprint_sha256
    assert blueprint_consistency["passed"] is True
    assert blueprint_consistency["pageBlueprintSha256"] == blueprint_sha256
    assert all(
        report["pageBlueprintSha256"] == blueprint_sha256
        for report in content_reports.values()
    )
    assert all(
        report["evidenceMapSha256"] == evidence_map["evidenceMapSha256"]
        and report["grounding"]["passed"] is True
        for report in content_reports.values()
    )
    agent_state = json.loads(
        (project / "agent" / "runtime-state.json").read_text(encoding="utf-8")
    )
    page_writes = []
    for tool_path in (project / "agent" / "tool-calls").glob("*.json"):
        record = json.loads(tool_path.read_text(encoding="utf-8"))
        if record["toolName"] == "write_or_patch_slide_svg":
            page_writes.append(record)
            assert record["authorTurnId"]
            assert record["modelVersion"] == "fake-agent@v1"
    assert {record["currentPnn"] for record in page_writes} == {"P01", "P02"}
    assert result["usage"]["inputTokens"] > 0
    assert result["usage"]["outputTokens"] > 0
    assert agent_state["usage"]["turns"] >= 10
    assert (
        content_reports["design"]["subjectSha256"]
        == hashlib.sha256((project / "design_spec.md").read_bytes()).hexdigest()
    )
    final_roster_hash = hashlib.sha256()
    for svg in sorted((project / "svg_output").glob("*.svg")):
        final_roster_hash.update(svg.name.encode("utf-8"))
        final_roster_hash.update(svg.read_bytes())
    assert content_reports["final"]["subjectSha256"] == final_roster_hash.hexdigest()

    design_spec = (project / "design_spec.md").read_text(encoding="utf-8")
    assert "## I. Project Information" in design_spec
    assert "## X. Speaker Notes Requirements" in design_spec
    assert "## VII." not in design_spec
    assert design_spec.index("P01") < design_spec.index("P02")

    chart_svg = (project / "svg_output" / "slide_02.svg").read_text(encoding="utf-8")
    assert 'data-pptx-replace-with="chart"' in chart_svg
    assert "chart-plot-area: object=throughput-comparison" in chart_svg

    pptx = project / "exports" / "deck.pptx"
    assert content_reports["pptx"]["subjectSha256"] == hashlib.sha256(pptx.read_bytes()).hexdigest()
    with zipfile.ZipFile(pptx) as archive:
        names = set(archive.namelist())
        assert (
            len(
                [
                    name
                    for name in names
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                ]
            )
            == 2
        )
        assert any(name.startswith("ppt/charts/chart") for name in names)
        assert not any(name.startswith("ppt/notesSlides/") for name in names)

    visible_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((project / "svg_output").glob("*.svg"))
    )
    assert "AI 重生成指令" not in visible_text
    assert "Editable native presentation baseline" not in visible_text
    assert "请生成" not in visible_text


def test_enabled_notes_and_custom_animation_run_in_owned_order(tmp_path: Path) -> None:
    workflow = _payload()
    workflow["production"].update(
        {
            "proactiveSpeakerNotes": True,
            "proactiveCustomAnimations": True,
            "effectiveSpeakerNotes": "enabled",
            "effectiveCustomAnimations": "enabled",
        }
    )
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    request = {
        "schemaVersion": 2,
        "requestId": "issue-002-stage-e-notes-animation",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/conditional",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    [project] = (tmp_path / "generated").glob("conditional_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    events = (project / "validation" / "workflow-events.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "succeeded"
    assert (project / "notes" / "total.md").is_file()
    assert len([path for path in (project / "notes").glob("*.md") if path.name != "total.md"]) == 2
    assert (project / "animations.json").is_file()
    assert events.index('"stage": "notes"') < events.index('"stage": "animations"')
    assert events.index('"stage": "animations"') < events.index('"stage": "step7_finalize"')
    with zipfile.ZipFile(project / "exports" / "deck.pptx") as archive:
        names = set(archive.namelist())
        assert any(name.startswith("ppt/notesSlides/notesSlide") for name in names)


def test_narration_is_owned_by_generate_audio_and_cannot_be_claimed_by_exporter(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["production"].update(
        {
            "proactiveSpeakerNotes": True,
            "proactiveNarrationAudio": True,
            "effectiveSpeakerNotes": "enabled",
            "effectiveNarrationAudio": "enabled",
        }
    )
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    request = {
        "schemaVersion": 2,
        "requestId": "issue-002-stage-e-narration",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/narration",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    [project] = (tmp_path / "generated").glob("narration_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    events = (project / "validation" / "workflow-events.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "needs_manual"
    assert result["stage"] == "narration"
    assert result["errors"][0]["code"] == "NARRATION_CONFIRMATION_REQUIRED"
    assert (project / "exports" / "deck.pptx").is_file()
    assert "awaiting-one-shot-audio-decision" in events
    assert '"stage": "publish"' not in events


def test_explicit_visual_review_renders_and_passes_structured_reviewer(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["authoring"]["visualReviewRequired"] = True
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review@v1"
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    request = {
        "schemaVersion": 2,
        "requestId": "issue-002-stage-e-visual-review",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/visual-review",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    [project] = (tmp_path / "generated").glob("visual-review_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    review = json.loads((project / "validation" / "visual-review.json").read_text(encoding="utf-8"))
    events = (project / "validation" / "workflow-events.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "succeeded"
    assert result["stage"] == "publish"
    assert review["passed"] is True
    assert review["issues"] == []
    assert review["reviewRound"] == 1
    assert (project / ".preview" / "round-1" / "contact-sheet.png").is_file()
    assert len(list((project / ".preview" / "round-1").glob("slide_*.png"))) == 2
    assert (project / "agent" / "visual-reviews" / "round-1.json").is_file()
    assert '"stage": "visual_review"' in events
    assert '"action": "passed"' in events
    assert (project / "exports" / "deck.pptx").is_file()


class _VisualRepairFixtureProvider:
    provider_name = "visual-repair-fixture"

    def __init__(self, *, clear_on_second_review: bool = True) -> None:
        self.delegate = DeterministicPresentationAgentProvider()
        self.clear_on_second_review = clear_on_second_review
        self.visual_calls = 0

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        completion = self.delegate.complete(
            messages,
            response_format=response_format,
            max_completion_tokens=max_completion_tokens,
        )
        if not any(
            "Visual Review Agent" in str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        ):
            return completion
        self.visual_calls += 1
        payload = json.loads(completion.content)
        if self.visual_calls == 1 or not self.clear_on_second_review:
            payload.update(
                {
                    "passed": False,
                    "issues": [
                        {
                            "issueId": "VR01",
                            "category": "hierarchy",
                            "severity": "blocking",
                            "scope": "page",
                            "pnn": "P01",
                            "owner": "executor",
                            "message": "P01 headline and evidence panel have equal visual weight.",
                            "region": "P01 title/evidence panel",
                            "suggestedAction": (
                                "Strengthen the title-to-evidence hierarchy without changing copy."
                            ),
                        }
                    ],
                    "summary": "P01 hierarchy blocks a clean visual reading order.",
                }
            )
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return TextCompletion(
            content=rendered,
            model="visual-repair-fixture@v1",
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=max(1, len(rendered) // 4),
        )


def test_visual_blocking_observation_repairs_owned_page_and_rereviews(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["authoring"]["visualReviewRequired"] = True
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review@v1"
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    provider = _VisualRepairFixtureProvider()

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        tmp_path / "visual-repair_ppt169_20260818",
        WorkflowRequestV2.model_validate(workflow),
        text_provider=provider,
    )

    project = tmp_path / "visual-repair_ppt169_20260818"
    result = outcome["result"]
    round_one = json.loads(
        (project / "validation" / "visual-review-round-1.json").read_text(
            encoding="utf-8"
        )
    )
    final_review = json.loads(
        (project / "validation" / "visual-review.json").read_text(encoding="utf-8")
    )
    scene = json.loads(
        (project / "agent" / "scene-graphs" / "P01.json").read_text(encoding="utf-8")
    )
    stale = json.loads(
        (project / "validation" / "agent-stale.json").read_text(encoding="utf-8")
    )

    assert result.status == "succeeded"
    assert provider.visual_calls == 2
    assert round_one["passed"] is False
    assert round_one["issues"][0]["category"] == "hierarchy"
    assert final_review["passed"] is True
    assert final_review["reviewRound"] == 2
    assert VisualReviewReport.model_validate(final_review).passed is True
    assert scene["authorAttempt"] == 2
    assert len(list((project / ".preview").glob("round-*/contact-sheet.png"))) == 2
    assert any(entry["pnn"] == "P01" for entry in stale["entries"])
    final_gate = json.loads(
        (project / "validation" / "receipts" / "final-svg-gate.json").read_text(
            encoding="utf-8"
        )
    )
    assert final_gate["payload"]["rerunAfterVisualRepairRound"] == 1
    assert final_gate["subjectSha256"] != final_gate["payload"][
        "stalePreviousSubjectSha256"
    ]


def test_visual_review_stops_without_export_when_round_two_remains_blocking(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["authoring"]["visualReviewRequired"] = True
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review@v1"
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    provider = _VisualRepairFixtureProvider(clear_on_second_review=False)

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        tmp_path / "visual-blocked_ppt169_20260818",
        WorkflowRequestV2.model_validate(workflow),
        text_provider=provider,
    )

    project = tmp_path / "visual-blocked_ppt169_20260818"
    result = outcome["result"]
    final_review = json.loads(
        (project / "validation" / "visual-review.json").read_text(encoding="utf-8")
    )

    assert result.status == "needs_manual"
    assert result.stage == "visual_review"
    assert [error.code for error in result.errors] == ["VISUAL_REVIEW_BLOCKING"]
    assert provider.visual_calls == 2
    assert final_review["reviewRound"] == 2
    assert final_review["passed"] is False
    assert not (project / "exports" / "deck.pptx").exists()
    assert not (project / "canonical-project-bundle.zip").exists()
    assert not (project / "validation" / "receipts" / "visual-review.json").exists()


def test_deterministic_template_fallback_is_disclosed_without_agent_evidence(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["profile"] = "deterministic-template"
    workflow["authoring"] = {
        "mode": "deterministic-template",
        "policyVersion": "presentation-authoring@v1",
        "fallbackReason": "operator-feature-flag",
        "disclosure": "template-limited-editable-draft",
        "visualReviewPolicyVersion": "visual-review-disabled@v1",
        "visualReviewRequired": False,
    }
    workflow["versions"]["prompt"] = "deterministic-template@v1"
    workflow["runtime"]["allowedTools"] = [
        "read-source",
        "write-project",
        "run-vendored-script",
        "start-live-preview",
    ]
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    request = {
        "schemaVersion": 2,
        "requestId": "issue-003-template-fallback",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/template-fallback",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    [project] = (tmp_path / "generated").glob("template-fallback_ppt169_*")
    result = json.loads((project / "workflow-result.json").read_text(encoding="utf-8"))
    events = (project / "validation" / "workflow-events.jsonl").read_text(
        encoding="utf-8"
    )
    receipt = json.loads(
        (project / "validation" / "receipts" / "first-page-gate.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["status"] == "succeeded"
    assert result["profile"] == "deterministic-template"
    assert result["authoringMode"] == "deterministic-template"
    assert result["authoringDisclosure"] == "template-limited-editable-draft"
    assert result["usage"]["inputTokens"] == 0
    assert result["usage"]["outputTokens"] == 0
    assert result["usage"]["costMicrounits"] == 0
    assert receipt["payload"]["authoringMode"] == "deterministic-template"
    assert receipt["payload"]["fallbackReason"] == "operator-feature-flag"
    assert "template-authored-limited-draft" in events
    assert "main-presentation-agent" not in events
    assert not (project / "agent").exists()
    assert (project / "exports" / "deck.pptx").is_file()
