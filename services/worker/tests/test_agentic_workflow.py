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
    _fit_text,
)
from instant_ppt_worker.providers import TextCompletion
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.visual_review_runtime import VisualReviewReport
from instant_ppt_worker.workflow_models import WorkflowRequestV2

from .test_workflow_contracts import _payload

ROOT = Path(__file__).resolve().parents[3]


def test_fixture_text_fit_wraps_without_tiny_type_or_content_loss() -> None:
    value = (
        "全面开放前，我们进行了迄今最密集的安全评估，包括大规模红队测试、"
        "与外部专家合作开展的严格能力与防护测试。"
    )

    fitted, size = _fit_text(value, 456, 250, 25)

    assert size >= 15
    assert "\n" in fitted
    assert "".join(fitted.split()) == "".join(value.split())


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


def test_sentences_skip_document_metadata_and_preserved_price_notes() -> None:
    fragments = [
        {
            "fragmentId": "metadata",
            "kind": "paragraph",
            "text": (
                "OpenAI 官方公告中文译版\n"
                "本文“可用性与定价”部分保留 7 月 9 日首发时的原始价格。\n"
                "__原文发布日期：__2026 年 7 月 9 日\n"
                "2026 年 7 月 30 日更新：Luna 的价格下调 80%。"
            ),
        }
    ]

    sentences = [text for text, _ in workflow_module._sentences(fragments)]

    assert sentences == ["2026 年 7 月 30 日更新：Luna 的价格下调 80%。"]


def test_data_page_defaults_to_metric_cards_without_native_chart() -> None:
    workflow = _payload()
    request = WorkflowRequestV2.model_validate(workflow)
    fragments = [
        fragment.model_dump(by_alias=True, mode="json")
        for artifact in request.sources.artifacts
        for fragment in artifact.fragments
    ]

    deck, plan = workflow_module._build_deck(request, fragments)

    assert request.production.native_charts is False
    assert request.outline[1].role == "data"
    assert deck.slides[1].title == request.outline[1].title
    assert plan["roster"][1]["chart"] is None


def test_data_slides_bind_distinct_benchmark_series() -> None:
    workflow = _payload()
    workflow["production"]["nativeCharts"] = True
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
        base["title"],
        base["title"],
        base["title"],
    ]
    assert len({tuple(slide["chart"]["values"]) for slide in plan["roster"][1:]}) == 3


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
    fragments = workflow_module._markdown_table_series(markdown_path.read_text(encoding="utf-8"))
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
    assert not (project / "deck-plan.json").exists()
    assert (project / "design_spec.md").is_file()
    rendered = [
        path.read_text(encoding="utf-8") for path in sorted((project / "svg_output").glob("*.svg"))
    ]
    assert len(rendered) == len(workflow["outline"])
    assert all("ISSUE-002 最终用户" in svg for svg in rendered)


def test_default_agentic_vertical_slice_exports_native_chart(tmp_path: Path) -> None:
    workflow = _payload()
    workflow["production"]["nativeCharts"] = True
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
    assert '"toolName":"request_visual_review"' not in events
    assert not (project / "agent" / "visual-reviews").exists()
    assert not (project / "validation" / "visual-review.json").exists()

    evidence_map = json.loads(
        (project / "analysis" / "evidence-map.json").read_text(encoding="utf-8")
    )
    strategist_receipt = json.loads(
        (project / "agent" / "phase-receipts" / "strategist.json").read_text(encoding="utf-8")
    )
    release_trace = json.loads(
        (project / "validation" / "release-trace.json").read_text(encoding="utf-8")
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
    assert strategist_receipt["status"] == "completed"
    assert strategist_receipt["turnIds"]
    assert (project / "agent" / "turns" / f"{strategist_receipt['turnIds'][-1]}.json").is_file()
    assert release_trace["passed"] is True
    assert not (project / "analysis" / "page-blueprint.v1.json").exists()
    assert not (project / "validation" / "page-blueprint-support.json").exists()
    assert all(
        report["evidenceMapSha256"] == evidence_map["evidenceMapSha256"]
        and report["grounding"]["passed"] is True
        for report in content_reports.values()
    )
    agent_state = json.loads((project / "agent" / "runtime-state.json").read_text(encoding="utf-8"))
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
    assert "chart-plot-area: object=source-chart-p02" in chart_svg

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


def test_gpt56_six_page_chinese_outline_bypasses_lexical_blueprint_gate(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    source_text = (ROOT / "tests/OpenAI_GPT-5.6_发布公告_中文版_2026-07-09.md").read_text(
        encoding="utf-8"
    )
    fragment = workflow["sources"]["artifacts"][0]["fragments"][0]
    fragment.update(
        {
            "kind": "paragraph",
            "text": source_text,
            "textSha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        }
    )
    roles_and_titles = [
        ("cover", "GPT-5.6 发布要点"),
        ("content", "模型家族概览"),
        ("data", "能力与效率表现"),
        ("content", "设计判断力"),
        ("risk_action", "安全边界与部署建议"),
        ("ending", "试点决策与下一步"),
    ]
    workflow["outline"] = [
        {
            "outlineSlideId": deterministic_ulid(
                hashlib.sha256(f"issue004-outline-{order}".encode()).hexdigest()
            ),
            "slideId": deterministic_ulid(
                hashlib.sha256(f"issue004-slide-{order}".encode()).hexdigest()
            ),
            "pnn": f"P{order:02d}",
            "order": order,
            "role": role,
            "title": title,
            "audienceQuestion": f"受众应如何理解“{title}”并形成决策？",
        }
        for order, (role, title) in enumerate(roles_and_titles, start=1)
    ]
    workflow["production"]["nativeCharts"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    request = {
        "schemaVersion": 2,
        "requestId": "issue-004-gpt56-six-page",
        "operation": "generatePptxDefault",
        "workspaceRoot": str(tmp_path),
        "outputKey": "generated/issue004-gpt56",
        "workflow": workflow,
    }

    response, exit_code = run_request(json.dumps(request, ensure_ascii=False))

    assert exit_code == 0, response.error.model_dump(mode="json") if response.error else response
    [project] = (tmp_path / "generated").glob("issue004-gpt56_ppt169_*")
    assert not (project / "analysis" / "page-blueprint.v1.json").exists()
    assert not (project / "validation" / "page-blueprint-support.json").exists()
    assert len(list((project / "svg_output").glob("slide_*.svg"))) == 6
    assert (project / "exports" / "deck.pptx").is_file()
    p02 = (project / "svg_output" / "slide_02.svg").read_text(encoding="utf-8")
    p04 = (project / "svg_output" / "slide_04.svg").read_text(encoding="utf-8")
    assert "模型家族概览" in p02
    assert "设计判断力" in p04
    with zipfile.ZipFile(project / "exports" / "deck.pptx") as archive:
        assert any(name.startswith("ppt/charts/chart") for name in archive.namelist())


def test_executor_does_not_start_before_design_confirmation(tmp_path: Path) -> None:
    workflow = _payload()
    workflow["confirmation"]["delegationScope"].remove("strategist-design-and-lock")
    project = tmp_path / "awaiting-design-confirmation_ppt169_20260827"

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        project,
        WorkflowRequestV2.model_validate(workflow),
    )

    assert outcome["result"].status == "awaiting_design_confirmation"
    assert (project / "design_spec.md").is_file()
    assert not (project / "spec_lock.md").exists()
    assert list((project / "svg_output").glob("slide_*.svg")) == []


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
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review-adaptive@v2"
    workflow["authoring"]["visualReviewMaxRounds"] = 5
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


class _LaterPageGateFixtureProvider:
    provider_name = "later-page-gate-fixture"

    def __init__(self) -> None:
        self.delegate = DeterministicPresentationAgentProvider()
        self.inserted_p02_gate = False

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
        payload = json.loads(completion.content)
        if (
            payload.get("terminationReason") == "p02-agent-authoring-complete"
            and not self.inserted_p02_gate
        ):
            self.inserted_p02_gate = True
            payload = {
                "schemaVersion": 1,
                "role": "executor",
                "action": "tool",
                "toolName": "run_svg_gate",
                "arguments": {"pnn": "P02"},
                "reason": "Verify the later page current hash before completion.",
                "terminationReason": None,
            }
            rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            return TextCompletion(
                content=rendered,
                model=completion.model,
                prompt_tokens=completion.prompt_tokens,
                completion_tokens=max(1, len(rendered) // 4),
            )
        return completion


def test_later_executor_page_may_run_bounded_page_local_svg_gate(tmp_path: Path) -> None:
    workflow = _payload()
    workflow["authoring"]["visualReviewRequired"] = True
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review@v1"
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    provider = _LaterPageGateFixtureProvider()

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        tmp_path / "later-page-gate_ppt169_20260823",
        WorkflowRequestV2.model_validate(workflow),
        text_provider=provider,
    )

    project = tmp_path / "later-page-gate_ppt169_20260823"
    p02_gates = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "agent" / "tool-calls").glob("*.json")
        if (
            (record := json.loads(path.read_text(encoding="utf-8")))["toolName"] == "run_svg_gate"
            and record["currentPnn"] == "P02"
        )
    ]

    assert outcome["result"].status == "succeeded"
    assert provider.inserted_p02_gate is True
    assert len(p02_gates) == 1
    assert p02_gates[0]["observation"]["report"]["passed"] is True
    assert p02_gates[0]["observation"]["report"]["methodLevel"][0]["code"] == (
        "SVG_PAGE_LOCAL_VALIDATED"
    )


def test_blocking_final_svg_gate_is_repaired_by_the_owned_page_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _payload()
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    original_checker = workflow_module._run_final_svg_checker
    checker_calls = 0

    def injected_checker(
        workspace_root: Path,
        project: Path,
        *,
        allow_failure: bool = False,
    ) -> dict[str, Any]:
        nonlocal checker_calls
        checker_calls += 1
        if checker_calls == 1:
            assert allow_failure is True
            return {
                "summary": {"errors": 1, "warnings": 0},
                "categories": {
                    "blocking": {
                        "count": 1,
                        "issues": [
                            {
                                "file": "slide_02.svg",
                                "code": "TEXT_OVERFLOW",
                                "message": "P02 body exceeds its owned content bounds.",
                            }
                        ],
                    }
                },
                "files": [],
                "_commandError": "fixture final SVG checker failed",
            }
        return original_checker(
            workspace_root,
            project,
            allow_failure=allow_failure,
        )

    monkeypatch.setattr(workflow_module, "_run_final_svg_checker", injected_checker)
    project = tmp_path / "final-svg-repair_ppt169_20260823"

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        project,
        WorkflowRequestV2.model_validate(workflow),
    )

    repair_writes = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "agent" / "tool-calls").glob("*.json")
        if (
            (record := json.loads(path.read_text(encoding="utf-8")))["toolName"]
            == "write_or_patch_slide_svg"
            and record["currentPnn"] == "P02"
            and record["stage"] == "svg-gate-repair"
        )
    ]
    repair_gates = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "agent" / "tool-calls").glob("*.json")
        if (
            (record := json.loads(path.read_text(encoding="utf-8")))["toolName"] == "run_svg_gate"
            and record["currentPnn"] == "P02"
            and record["stage"] == "svg-gate-repair"
        )
    ]
    receipt = json.loads(
        (project / "validation" / "receipts" / "final-svg-gate.json").read_text(encoding="utf-8")
    )

    assert outcome["result"].status == "succeeded"
    assert checker_calls == 3
    assert len(repair_writes) == 1
    assert len(repair_gates) == 1
    assert repair_gates[0]["observation"]["report"]["passed"] is True
    assert repair_gates[0]["observation"]["report"]["methodLevel"][0]["code"] == (
        "SVG_PAGE_FINAL_VALIDATED"
    )
    assert repair_writes[0]["authorAttempt"] == 2
    assert repair_writes[0]["observation"]["authoringMode"] == "validated-direct-svg"
    assert receipt["payload"]["blockingCount"] == 0
    assert (project / "agent" / "phase-receipts" / "svg-gate-repair-r1-p02.json").is_file()


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
            pnn = "P02" if not self.clear_on_second_review and self.visual_calls == 2 else "P01"
            payload.update(
                {
                    "issues": [
                        {
                            "category": "hierarchy",
                            "severity": "blocking",
                            "pnn": pnn,
                            "message": (
                                f"{pnn} headline and evidence panel have equal visual weight."
                            ),
                            "region": f"{pnn} title/evidence panel",
                            "suggestedAction": (
                                "Strengthen the title-to-evidence hierarchy without changing copy."
                            ),
                        }
                    ],
                }
            )
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return TextCompletion(
            content=rendered,
            model="visual-repair-fixture@v1",
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=max(1, len(rendered) // 4),
        )


class _DirectSvgVisualRepairFixtureProvider(_VisualRepairFixtureProvider):
    """Named fixture retained to assert the Direct SVG-only repair path."""

    def __init__(self, project: Path) -> None:
        del project
        super().__init__()


class _V3VisualRepairFixtureProvider(_VisualRepairFixtureProvider):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        completion = super().complete(
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
        payload = json.loads(completion.content)
        if payload.get("issues"):
            payload["issues"][0].update(
                {
                    "category": "alignment-rhythm-balance",
                    "message": "P01 title overlaps a key element and is clipped.",
                    "region": "P01 page title",
                    "suggestedAction": "Move the title one pixel without changing copy.",
                    "targetElementIds": ["page-title"],
                }
            )
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return TextCompletion(
            content=rendered,
            model="v3-visual-repair-fixture@v1",
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=max(1, len(rendered) // 4),
        )


class _PostVisualSvgRepairFixtureProvider(_VisualRepairFixtureProvider):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        completion = super().complete(
            messages,
            response_format=response_format,
            max_completion_tokens=max_completion_tokens,
        )
        if not any(
            "svg-gate-repair-post-visual" in str(message.get("content") or "")
            for message in messages
        ):
            return completion
        payload = json.loads(completion.content)
        if payload.get("toolName") != "write_or_patch_slide_svg":
            return completion
        svg = str(payload["arguments"]["svg"])
        payload["arguments"]["svg"] = svg.replace(
            "<svg ", '<svg data-post-visual-repair="true" ', 1
        )
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return TextCompletion(
            content=rendered,
            model="post-visual-svg-repair-fixture@v1",
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
        (project / "validation" / "visual-review-round-1.json").read_text(encoding="utf-8")
    )
    final_review = json.loads(
        (project / "validation" / "visual-review.json").read_text(encoding="utf-8")
    )
    repair_writes = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "agent" / "tool-calls").glob("*.json")
        if (
            (record := json.loads(path.read_text(encoding="utf-8")))["toolName"]
            == "write_or_patch_slide_svg"
            and record["currentPnn"] == "P01"
            and record["stage"] == "visual-repair"
        )
    ]
    stale = json.loads((project / "validation" / "agent-stale.json").read_text(encoding="utf-8"))

    assert result.status == "succeeded"
    assert provider.visual_calls == 2
    assert round_one["passed"] is False
    assert round_one["issues"][0]["category"] == "hierarchy"
    assert final_review["passed"] is True
    assert final_review["reviewRound"] == 2
    assert VisualReviewReport.model_validate(final_review).passed is True
    assert len(repair_writes) == 1
    assert repair_writes[0]["authorAttempt"] == 2
    assert repair_writes[0]["observation"]["authoringMode"] == "validated-direct-svg"
    assert len(list((project / ".preview").glob("round-*/contact-sheet.png"))) == 2
    assert any(entry["pnn"] == "P01" for entry in stale["entries"])
    final_gate = json.loads(
        (project / "validation" / "receipts" / "final-svg-gate.json").read_text(encoding="utf-8")
    )
    assert final_gate["payload"]["rerunAfterVisualRepairRound"] == 1
    assert final_gate["subjectSha256"] != final_gate["payload"]["stalePreviousSubjectSha256"]


def test_visual_repair_reruns_and_repairs_final_svg_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _payload()
    workflow["authoring"]["visualReviewRequired"] = True
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review@v1"
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    provider = _PostVisualSvgRepairFixtureProvider()
    original_checker = workflow_module._run_final_svg_checker
    checker_calls = 0

    def injected_checker(
        workspace_root: Path,
        project: Path,
        *,
        allow_failure: bool = False,
    ) -> dict[str, Any]:
        nonlocal checker_calls
        checker_calls += 1
        if checker_calls == 2:
            assert allow_failure is True
            return {
                "summary": {"errors": 1, "warnings": 0},
                "categories": {
                    "blocking": {
                        "count": 1,
                        "issues": [
                            {
                                "file": "slide_01.svg",
                                "code": "TEXT_OVERFLOW",
                                "message": "P01 visual repair pushed title beyond the canvas.",
                            }
                        ],
                    }
                },
                "files": [],
                "_commandError": "fixture post-visual SVG checker failed",
            }
        return original_checker(
            workspace_root,
            project,
            allow_failure=allow_failure,
        )

    monkeypatch.setattr(workflow_module, "_run_final_svg_checker", injected_checker)
    project = tmp_path / "visual-post-svg-repair_ppt169_20260826"

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        project,
        WorkflowRequestV2.model_validate(workflow),
        text_provider=provider,
    )

    assert outcome["result"].status == "succeeded"
    assert checker_calls >= 3
    phase_receipt = (
        project / "agent" / "phase-receipts" / "svg-gate-repair-post-visual-v1-r1-p01.json"
    )
    assert phase_receipt.is_file()
    repair_writes = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "agent" / "tool-calls").glob("*.json")
        if (
            (record := json.loads(path.read_text(encoding="utf-8")))["toolName"]
            == "write_or_patch_slide_svg"
            and record["currentPnn"] == "P01"
            and record["stage"] == "svg-gate-repair"
        )
    ]
    assert len(repair_writes) == 1


def test_visual_review_repairs_direct_svg_without_switching_authoring_mode(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["authoring"]["visualReviewRequired"] = True
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review@v1"
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    project = tmp_path / "visual-repair-direct-svg_ppt169_20260825"
    provider = _DirectSvgVisualRepairFixtureProvider(project)

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        project,
        WorkflowRequestV2.model_validate(workflow),
        text_provider=provider,
    )

    assert outcome["result"].status == "succeeded"
    assert provider.visual_calls == 2
    render_round_one = json.loads(
        (project / "validation" / "visual-render-round-1.json").read_text(encoding="utf-8")
    )
    assert {page["authoringMode"] for page in render_round_one["pages"]} == {"validated-direct-svg"}
    writes = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "agent" / "tool-calls").glob("*.json")
    ]
    p01_writes = [
        record
        for record in writes
        if record["toolName"] == "write_or_patch_slide_svg" and record["currentPnn"] == "P01"
    ]
    assert {record["stage"] for record in p01_writes} >= {"executor", "visual-repair"}
    assert {record["observation"]["authoringMode"] for record in p01_writes} == {
        "validated-direct-svg"
    }


def test_visual_review_stops_without_export_when_final_round_remains_blocking(
    tmp_path: Path,
) -> None:
    workflow = _payload()
    workflow["authoring"]["visualReviewRequired"] = True
    workflow["authoring"]["visualReviewPolicyVersion"] = "visual-review-adaptive@v2"
    workflow["authoring"]["visualReviewMaxRounds"] = 5
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
    assert provider.visual_calls == 3
    assert final_review["reviewRound"] == 1
    assert final_review["passed"] is False
    decision = json.loads(
        (project / "agent" / "visual-reviews" / "decision-round-3.json").read_text(encoding="utf-8")
    )
    assert decision["reason"] == "stalled-two-rounds"
    assert decision["bestRound"] == 1
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
    events = (project / "validation" / "workflow-events.jsonl").read_text(encoding="utf-8")
    receipt = json.loads(
        (project / "validation" / "receipts" / "first-page-gate.json").read_text(encoding="utf-8")
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


@pytest.mark.parametrize(
    ("level", "max_rounds", "expected_calls"),
    [("standard", 1, 1), ("final", 2, 2)],
)
def test_v3_visual_review_is_opt_in_atomic_and_bounded(
    tmp_path: Path,
    level: str,
    max_rounds: int,
    expected_calls: int,
) -> None:
    workflow = _payload()
    workflow["authoring"].update(
        {
            "visualReviewRequired": True,
            "visualReviewPolicyVersion": "visual-review-opt-in@v3",
            "visualReviewLevel": level,
            "visualReviewMaxRounds": max_rounds,
            "authoringModel": "fake-agent@v1",
            "visualReviewModel": "fake-agent@v1",
        }
    )
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    provider = _V3VisualRepairFixtureProvider()
    project = tmp_path / f"visual-v3-{level}_ppt169_20260827"

    outcome = workflow_module.run_default_workflow(
        tmp_path,
        project,
        WorkflowRequestV2.model_validate(workflow),
        text_provider=provider,
    )

    review = json.loads(
        (project / "validation" / "visual-review.json").read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (project / "validation" / "receipts" / "visual-review.json").read_text(
            encoding="utf-8"
        )
    )
    repair_call = next(
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "agent" / "tool-calls").glob("*.json")
        if json.loads(path.read_text(encoding="utf-8")).get("stage") == "visual-repair"
        and json.loads(path.read_text(encoding="utf-8")).get("toolName")
        == "write_or_patch_slide_svg"
    )

    assert outcome["result"].status == "succeeded"
    assert provider.visual_calls == expected_calls
    assert review["policyVersion"] == "visual-review-opt-in@v3"
    assert review["reviewLevel"] == level
    assert review["reviewCallCount"] == expected_calls
    assert review["fixedPages"] == ["P01"]
    assert review["rolledBackPages"] == []
    assert receipt["status"] in {"passed", "passed-with-warnings"}
    assert (project / "agent" / "visual-reviews" / "baseline-svg" / "slide_01.svg").is_file()
    assert repair_call["observation"]["visualRepair"]["targetElementIds"] == [
        "page-title"
    ]
    assert {
        change["attribute"]
        for change in repair_call["observation"]["visualRepair"]["changes"]
    } <= {"x", "y", "width", "height", "font-size"}
    if level == "standard":
        assert not (project / "validation" / "visual-review-round-2.json").exists()
    else:
        assert len(list((project / ".preview" / "round-2").glob("slide_*.png"))) == 1
