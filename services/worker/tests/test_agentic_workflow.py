import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import instant_ppt_worker.agentic_workflow as workflow_module
import pytest
from instant_ppt_worker.adapter import run_request
from instant_ppt_worker.errors import CONTENT_QA_FAILED, AdapterError
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.workflow_models import WorkflowRequestV2

from .test_workflow_contracts import _payload


def test_conflicting_approved_chart_facts_are_blocking() -> None:
    fragments = [
        {"text": "Sol: 418 req/s"},
        {"text": "Sol: 999 req/s"},
    ]
    with pytest.raises(AdapterError) as captured:
        workflow_module._chart_values(fragments)
    assert captured.value.code == CONTENT_QA_FAILED


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
    assert '"author": "current-main-agent"' in events
    assert "quick-generate" not in events

    evidence_map = json.loads(
        (project / "analysis" / "evidence-map.json").read_text(encoding="utf-8")
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
    assert all(
        report["evidenceMapSha256"] == evidence_map["evidenceMapSha256"]
        and report["grounding"]["passed"] is True
        for report in content_reports.values()
    )
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


def test_explicit_visual_review_renders_then_waits_for_review_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _payload()
    workflow["production"]["visualReview"] = True
    workflow["runtime"]["allowSubagentReview"] = True
    workflow["runtime"]["previewIdleTimeoutSeconds"] = 1
    original_run = workflow_module._run

    def run_with_render_receipt(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if any(str(value).endswith("visual_review.py") for value in command):
            return subprocess.CompletedProcess(command, 0, '{"rendered":2}', "")
        return original_run(command, **kwargs)

    monkeypatch.setattr(workflow_module, "_run", run_with_render_receipt)
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
    assert result["status"] == "needs_manual"
    assert result["stage"] == "visual_review"
    assert review["status"] == "needs-agent-review"
    assert review["explicitOptIn"] is True
    assert '"stage": "visual_review"' in events
    assert not (project / "exports" / "deck.pptx").exists()
