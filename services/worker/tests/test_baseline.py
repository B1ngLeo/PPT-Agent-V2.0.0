import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from instant_ppt_domain.runtime_contract import (
    PROCESS_EXPORT_TASK,
    PROCESS_GENERATION_TASK,
    PROCESS_SLIDE_REGENERATION_TASK,
)
from instant_ppt_worker.celery_app import celery_app
from instant_ppt_worker.models import DeckPlan
from instant_ppt_worker.renderer import render_deck, render_slide_candidate
from instant_ppt_worker.settings import WorkerContract
from PIL import Image


def test_worker_contract_is_versioned_and_immutable() -> None:
    contract = WorkerContract()
    assert contract.schema_version == 1
    assert contract.adapter_name == "ppt-master-engine-adapter"
    assert contract.engine_version.startswith("ppt-master@v4.7.0")


def test_default_lifecycle_tasks_use_v2_names_and_agentic_route() -> None:
    routes = celery_app.conf.task_routes
    assert routes[PROCESS_GENERATION_TASK] == {"queue": "agentic"}
    assert PROCESS_EXPORT_TASK == "instant_ppt.v2.process_export"
    assert PROCESS_SLIDE_REGENERATION_TASK == "instant_ppt.v2.process_slide_regeneration"


def test_long_cjk_cover_copy_is_wrapped_before_upstream_qa(tmp_path: Path) -> None:
    deck = DeckPlan.model_validate(
        {
            "schemaVersion": 1,
            "snapshotId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "title": "G06 生产构建端到端恢复与不可变发布验证",
            "modeId": "native",
            "templateBinding": {
                "schemaVersion": 1,
                "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
                "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FAB",
                "compatibilityVersion": "ppt-master@v4.7.0",
                "roleBindings": {"cover": "layout-cover"},
            },
            "slides": [
                {
                    "schemaVersion": 1,
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAC",
                    "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAD",
                    "order": 0,
                    "role": "cover",
                    "title": "G06 生产构建端到端恢复与不可变发布验证",
                    "body": [
                        "主题：GPT5.6 官方公告解读；沟通目标：帮助关注AI大模型动态的技术从业者、"
                        "产品经理与科技爱好者形成“梳理GPT5.6官方公告的核心要点，介绍新模型能力、"
                        "关键改进与潜在影响”的初步判断"
                    ],
                    "editable": True,
                }
            ],
        }
    )
    result = render_slide_candidate(deck, tmp_path, visual_index=0)
    report = json.loads(result["qa"].read_text(encoding="utf-8"))
    assert report["summary"]["errors"] == 0
    assert report["summary"]["passed"] == 1
    svg = result["svg"].read_text(encoding="utf-8")
    assert svg.count("<tspan") >= 2
    assert "关键改进与潜在影响”的初步判断" in svg

    deck_plan_path = tmp_path / "deck-plan.json"
    deck_plan_path.write_text(deck.model_dump_json(by_alias=True), encoding="utf-8")
    render_deck(
        deck_plan_path,
        tmp_path / "full-deck",
        organization_id="01ARZ3NDEKTSV4RRFFQ69G5FAE",
        created_at="2026-08-16T00:00:00Z",
    )
    package_report = json.loads(
        (tmp_path / "full-deck/validation/pptx-package-qa.json").read_text(encoding="utf-8")
    )
    assert package_report["passed"] is True
    assert package_report["matchedEditableTextCount"] == 2


def test_single_long_timeline_fact_is_centered_inside_safe_bounds(tmp_path: Path) -> None:
    deck = DeckPlan.model_validate(
        {
            "schemaVersion": 1,
            "snapshotId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "title": "GPT-5.6 公告解读",
            "modeId": "native",
            "templateBinding": {
                "schemaVersion": 1,
                "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
                "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FAB",
                "compatibilityVersion": "ppt-master@v4.7.0",
                "roleBindings": {"timeline": "free-design-timeline"},
            },
            "slides": [
                {
                    "schemaVersion": 1,
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAC",
                    "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAD",
                    "order": 0,
                    "role": "timeline",
                    "title": "效率提升路线",
                    "body": [
                        "在 Artificial Analysis Intelligence Index 上，Sol max 与 "
                        "Fable 5 相差 1 分，但时间减少 61%，预估成本约为一半。"
                    ],
                    "editable": True,
                }
            ],
        }
    )

    result = render_slide_candidate(deck, tmp_path, visual_index=0)
    report = json.loads(result["qa"].read_text(encoding="utf-8"))

    assert report["summary"]["errors"] == 0
    assert report["summary"]["passed"] == 1


def test_long_cjk_content_copy_is_wrapped_before_upstream_qa(tmp_path: Path) -> None:
    long_recommendation = (
        "建议：由关注AI大模型动态的技术从业者、产品经理与科技爱好者先对齐“梳理"
        "GPT5.6官方公告的核心要点，介绍新模型能力、关键改进与潜在影响”"
    )
    deck = DeckPlan.model_validate(
        {
            "schemaVersion": 1,
            "snapshotId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "title": "GPT5.6 官方公告解读",
            "modeId": "native",
            "templateBinding": {
                "schemaVersion": 1,
                "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
                "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FAB",
                "compatibilityVersion": "ppt-master@v4.7.0",
                "roleBindings": {"content": "free-design-content"},
            },
            "slides": [
                {
                    "schemaVersion": 1,
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAC",
                    "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAD",
                    "order": 0,
                    "role": "content",
                    "title": "公告概览与解读框架",
                    "body": [
                        "判断：本页需服务于GPT5.6官方公告解读的可执行选择",
                        long_recommendation,
                    ],
                    "editable": True,
                }
            ],
        }
    )

    result = render_slide_candidate(deck, tmp_path, visual_index=0)
    report = json.loads(result["qa"].read_text(encoding="utf-8"))
    svg = result["svg"].read_text(encoding="utf-8")
    visible_text = "".join(ET.fromstring(svg).itertext())

    assert report["summary"]["errors"] == 0
    assert report["summary"]["passed"] == 1
    assert svg.count("<tspan") >= 2
    assert long_recommendation in visible_text


def test_generated_cover_image_is_embedded_as_referenced_pptx_media(tmp_path: Path) -> None:
    deck = DeckPlan.model_validate(
        {
            "schemaVersion": 1,
            "snapshotId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "title": "AI 产品战略",
            "modeId": "native",
            "templateBinding": {
                "schemaVersion": 1,
                "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
                "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FAB",
                "compatibilityVersion": "ppt-master@v4.7.0",
                "roleBindings": {"cover": "layout-cover"},
            },
            "slides": [
                {
                    "schemaVersion": 1,
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAC",
                    "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAD",
                    "order": 0,
                    "role": "cover",
                    "title": "AI 产品战略",
                    "body": ["从洞察走向行动"],
                    "editable": True,
                }
            ],
        }
    )
    cover_path = tmp_path / "cover.png"
    Image.new("RGB", (1536, 1024), color=(32, 74, 135)).save(cover_path)
    deck_plan_path = tmp_path / "deck-plan-with-image.json"
    deck_plan_path.write_text(deck.model_dump_json(by_alias=True), encoding="utf-8")

    output = tmp_path / "deck-with-image"
    render_deck(
        deck_plan_path,
        output,
        organization_id="01ARZ3NDEKTSV4RRFFQ69G5FAE",
        created_at="2026-08-16T00:00:00Z",
        cover_image_path=cover_path,
    )

    report = json.loads(
        (output / "validation/pptx-package-qa.json").read_text(encoding="utf-8")
    )
    assert report["passed"] is True
    assert len(report["mediaParts"]) == 1
    assert report["mediaParts"] == report["mediaReferences"]
    assert report["unreferencedMediaParts"] == []
    with zipfile.ZipFile(output / "deck.pptx") as archive:
        assert archive.read(report["mediaParts"][0]).startswith(b"\x89PNG")
