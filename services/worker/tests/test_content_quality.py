import hashlib
import json
from pathlib import Path

import pytest
from instant_ppt_worker.content_quality import evaluate_deck
from instant_ppt_worker.errors import CONTENT_QA_FAILED, AdapterError
from instant_ppt_worker.grounding_quality import build_evidence_map
from instant_ppt_worker.models import DeckPlan
from instant_ppt_worker.renderer import render_deck, render_slide_candidate


def _deck(body: list[str], *, role: str = "content") -> DeckPlan:
    return DeckPlan.model_validate(
        {
            "schemaVersion": 1,
            "snapshotId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "title": "GPT-5.6 官方发布公告解读",
            "modeId": "native",
            "templateBinding": {
                "schemaVersion": 1,
                "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
                "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FAB",
                "compatibilityVersion": "ppt-master@v4.7.0",
                "roleBindings": {role: f"layout-{role}"},
            },
            "slides": [
                {
                    "schemaVersion": 1,
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAC",
                    "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAD",
                    "order": 0,
                    "role": role,
                    "title": "性能与基准",
                    "body": body,
                    "editable": True,
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "body,code",
    [
        (
            ["汇总公告中列出的核心能力更新项", "呈现公告披露的基准测试结果"],
            "CONTENT_AUTHOR_TASK_DOMINANT",
        ),
        (["待官方公告确认", "需官方数据，当前不可用"], "CONTENT_PLACEHOLDER_DOMINANT"),
        (["AI 重生成指令：把这一页写得更具体"], "CONTENT_ENGINEERING_TEXT_LEAK"),
    ],
)
def test_release_guard_blocks_issue_002_failure_modes(body: list[str], code: str) -> None:
    report = evaluate_deck(_deck(body), stage="test")
    assert report["passed"] is False
    assert code in {finding["code"] for finding in report["findings"]}


@pytest.mark.parametrize(
    "body",
    [
        ["每个 token 带来更多智能，并为最艰巨的工作按需提供更强能力。"],
        ["该流程无需提供额外凭据。"],
        ["如需确认细节，请查阅已批准的来源。"],
    ],
)
def test_release_guard_allows_non_placeholder_modal_phrases(body: list[str]) -> None:
    report = evaluate_deck(_deck(body), stage="test")

    assert report["passed"] is True, report


def test_representation_guard_ignores_layout_line_breaks_without_losing_characters() -> None:
    body = "约 70 万个 NVIDIA A100 Tensor Core GPU 等效小时的黑盒自动化红队测试。"
    deck = _deck([body])

    passing = evaluate_deck(
        deck,
        stage="final-svg",
        represented_text=(
            "性能与基准\n约 70 万个 NVIDIA A100\nTensor Core GPU 等效小时的黑盒自动化红队测试。"
        ),
    )
    rejected = evaluate_deck(
        deck,
        stage="final-svg",
        represented_text="性能与基准\n约 70 万个 NVIDIA A100\nTensor Core GPU 等效小时。",
    )

    assert passing["passed"] is True
    assert rejected["passed"] is False
    assert "CONTENT_REPRESENTATION_MISSING" in {finding["code"] for finding in rejected["findings"]}


def test_representation_guard_treats_markdown_escape_as_visible_punctuation() -> None:
    report = evaluate_deck(
        _deck([r"GPT\-5.6 已发布。"]),
        stage="final-svg",
        represented_text="性能与基准\nGPT-5.6 已发布。",
    )

    assert report["passed"] is True, report


def test_representation_guard_allows_label_and_body_text_box_split() -> None:
    report = evaluate_deck(
        _deck(["结论：围绕高价值场景形成可编辑决策初稿。"]),
        stage="final-svg",
        represented_text="性能与基准\n结论\n围绕高价值场景形成可编辑决策初稿。",
    )

    assert report["passed"] is True, report


def test_agent_representation_guard_can_require_structural_framing_only() -> None:
    deck = _deck(["Blueprint 中用于策划的完整长段落，不要求执行器逐字排版。"])
    slide_id = deck.slides[0].slide_id

    passing = evaluate_deck(
        deck,
        stage="final-svg",
        represented_text="性能与基准\n执行器浓缩后的可见正文",
        representation_requirements=[(slide_id, "title", "性能与基准")],
    )
    rejected = evaluate_deck(
        deck,
        stage="final-svg",
        represented_text="执行器浓缩后的可见正文",
        representation_requirements=[(slide_id, "title", "性能与基准")],
    )

    assert passing["passed"] is True, passing
    assert rejected["passed"] is False
    assert rejected["findings"][0]["field"] == "title"


def test_representation_guard_rejects_extra_visible_agent_instruction() -> None:
    deck = _deck(["已批准的可见结论"])

    report = evaluate_deck(
        deck,
        stage="final-svg",
        represented_text=("性能与基准\n已批准的可见结论\nSVG QA passed baseline"),
    )

    assert report["passed"] is False
    assert "CONTENT_ENGINEERING_TEXT_LEAK" in {finding["code"] for finding in report["findings"]}


def test_hash_bound_risk_receipt_prevents_dictionary_false_positive() -> None:
    deck = _deck(["风险边界：价格仍待核实，不应进入预算承诺", "行动：法务完成供应商报价复核"])
    text = deck.slides[0].body[0]
    reason = "用户明确要求保留风险与后续核验边界"
    receipt_hash = hashlib.sha256(
        json.dumps(
            {"slideId": deck.slides[0].slide_id, "text": text, "reason": reason},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    report = evaluate_deck(
        deck,
        stage="test",
        approved_exceptions={
            deck.slides[0].slide_id: [{"text": text, "reason": reason, "receiptHash": receipt_hash}]
        },
    )
    assert report["passed"] is True


def test_every_legacy_render_entry_is_guarded(tmp_path: Path) -> None:
    deck = _deck(["待填充", "待核实"])
    with pytest.raises(AdapterError) as candidate_error:
        render_slide_candidate(deck, tmp_path / "candidate", visual_index=0)
    assert candidate_error.value.code == CONTENT_QA_FAILED

    plan = tmp_path / "deck-plan.json"
    plan.write_text(deck.model_dump_json(by_alias=True), encoding="utf-8")
    with pytest.raises(AdapterError) as deck_error:
        render_deck(
            plan,
            tmp_path / "deck",
            organization_id="01ARZ3NDEKTSV4RRFFQ69G5FAE",
            created_at="2026-08-18T00:00:00Z",
        )
    assert deck_error.value.code == CONTENT_QA_FAILED


def test_allowed_fragment_id_cannot_support_an_unrelated_claim() -> None:
    deck = _deck(["Sol 实测吞吐为 418 req/s"])
    source_text = "性能与基准：Sol 实测吞吐为 418 req/s。"
    fragment = {
        "sourceArtifactId": "01ARZ3NDEKTSV4RRFFQ69G5FAE",
        "fragmentId": "fragment-1",
        "text": source_text,
        "textSha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }
    roster = [
        {
            "pnn": "P01",
            "role": "content",
            "factIds": ["fragment-1"],
            "chart": None,
        }
    ]
    evidence_map = build_evidence_map(
        deck,
        roster,
        [fragment],
        source_manifest_sha256="a" * 64,
    )
    passing = evaluate_deck(
        deck,
        stage="test-grounding",
        evidence_map=evidence_map,
        source_fragments=[fragment],
        source_manifest_sha256="a" * 64,
    )
    assert passing["passed"] is True

    # Keep the citation itself valid, but replace the visible claim and bind a
    # new map hash.  ID allowlisting alone must not turn this into support.
    claim = evidence_map["slides"][0]["claims"][1]
    claim["text"] = "Luna 实测吞吐为 999 req/s"
    claim["claimSha256"] = hashlib.sha256(claim["text"].encode("utf-8")).hexdigest()
    unhashed = {key: value for key, value in evidence_map.items() if key != "evidenceMapSha256"}
    evidence_map["evidenceMapSha256"] = hashlib.sha256(
        json.dumps(
            unhashed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    rejected = evaluate_deck(
        deck,
        stage="test-grounding",
        evidence_map=evidence_map,
        source_fragments=[fragment],
        source_manifest_sha256="a" * 64,
    )
    assert rejected["passed"] is False
    assert "CITATION_SEMANTICALLY_UNSUPPORTED" in {
        finding["code"] for finding in rejected["findings"]
    }


def test_approved_outline_title_is_structural_framing_not_a_source_claim() -> None:
    deck = _deck(["Sol 实测吞吐为 418 req/s"])
    source_text = "Sol 实测吞吐为 418 req/s。"
    fragment = {
        "sourceArtifactId": "01ARZ3NDEKTSV4RRFFQ69G5FAE",
        "fragmentId": "fragment-1",
        "text": source_text,
        "textSha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }
    evidence_map = build_evidence_map(
        deck,
        [
            {
                "pnn": "P01",
                "role": "content",
                "approvedOutlineTitle": "性能与基准",
                "factIds": ["fragment-1"],
                "chart": None,
            }
        ],
        [fragment],
        source_manifest_sha256="a" * 64,
    )

    report = evaluate_deck(
        deck,
        stage="test-grounding",
        evidence_map=evidence_map,
        source_fragments=[fragment],
        source_manifest_sha256="a" * 64,
    )

    assert report["passed"] is True
    assert evidence_map["slides"][0]["claims"][0]["claimType"] == ("approved-outline-framing")


def test_editorial_outlook_prefix_does_not_break_an_exact_source_citation() -> None:
    deck = _deck(
        [
            "结论：Sol 已提升长任务执行能力",
            "展望：Sol 将继续强化长任务执行能力",
            "行动：选择高价值场景开展受控验证",
        ]
    )
    source_text = "Sol 已提升长任务执行能力。Sol 将继续强化长任务执行能力。"
    fragment = {
        "sourceArtifactId": "01ARZ3NDEKTSV4RRFFQ69G5FAE",
        "fragmentId": "fragment-1",
        "text": source_text,
        "textSha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }
    evidence_map = build_evidence_map(
        deck,
        [
            {
                "pnn": "P01",
                "role": "ending",
                "approvedOutlineTitle": "性能与基准",
                "factIds": ["fragment-1"],
                "chart": None,
            }
        ],
        [fragment],
        source_manifest_sha256="a" * 64,
    )

    report = evaluate_deck(
        deck,
        stage="test-grounding",
        evidence_map=evidence_map,
        source_fragments=[fragment],
        source_manifest_sha256="a" * 64,
    )

    assert report["passed"] is True, report["findings"]
