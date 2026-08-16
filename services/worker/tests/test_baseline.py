import json
from pathlib import Path

from instant_ppt_worker.models import DeckPlan
from instant_ppt_worker.renderer import render_deck, render_slide_candidate
from instant_ppt_worker.settings import WorkerContract


def test_worker_contract_is_versioned_and_immutable() -> None:
    contract = WorkerContract()
    assert contract.schema_version == 1
    assert contract.adapter_name == "ppt-master-engine-adapter"
    assert contract.engine_version.startswith("ppt-master@v4.7.0")


def test_long_cjk_cover_copy_is_fitted_before_upstream_qa(tmp_path: Path) -> None:
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
                        "围绕生产构建端到端恢复与不可变发布验证给出清晰而可执行的核心论点"
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
