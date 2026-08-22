"""Hash-bound content release guard shared by every presentation lifecycle path."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from instant_ppt_worker.grounding_quality import evaluate_evidence_map
from instant_ppt_worker.models import DeckPlan, SlidePlan

CONTENT_REQUIRED_ROLES = frozenset(
    {
        "cover",
        "toc",
        "section",
        "content",
        "ending",
        "conclusion",
        "comparison",
        "timeline",
        "data",
        "chart",
        "table",
    }
)

ENGINEERING_TEXT_PATTERNS = (
    re.compile(r"editable\s+native\s+presentation\s+baseline", re.IGNORECASE),
    re.compile(r"connect\s+the\s+approved\s+evidence", re.IGNORECASE),
    re.compile(r"approved\s+evidence\s*[·|:\-]\s*blueprint", re.IGNORECASE),
    re.compile(r"AI\s*重生成指令[：:]", re.IGNORECASE),
    re.compile(r"本页已由\s*AI\s*重新生成并通过质量检查"),
    re.compile(r"(?:quality|package|svg)\s+(?:check|qa)\s+(?:passed|baseline)", re.IGNORECASE),
)

UNRESOLVED_PATTERNS = (
    re.compile(
        r"(?:待|(?<![按无如若所])需)"
        r"(?:官方(?:公告|原文|数据)?|补充|确认|核实|填充|完善|提供|获取|验证)"
    ),
    re.compile(r"内容待补充|数据待填充|核心结论[：:]?\s*待|未提供官方公告原文"),
    re.compile(r"\b(?:TBD|TK|PLACEHOLDER)\b", re.IGNORECASE),
)

AUTHOR_TASK_PATTERNS = (
    re.compile(
        r"^(?:本页(?:需要|将|应)?|请|需要|建议)?\s*"
        r"(?:介绍|汇总|呈现|梳理|说明|给出|整理|展示|概述|阐述|列出|补充|收集)"
        r"(?:公告|本页|相关|核心|主要|关键|具体|官方|产品|技术|数据|信息|结果|内容|更新|建议|行动|背景|影响)"
    ),
    re.compile(
        r"^(?:introduce|summarize|present|outline|describe|explain|list|gather|add)\b",
        re.IGNORECASE,
    ),
)


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _representation_normalized(value: str) -> str:
    """Ignore layout-only whitespace while retaining the exact visible character sequence."""

    unescaped = re.sub(r"\\([\\`*{}\[\]()#+.!_\-])", r"\1", html.unescape(value))
    return "".join(unescaped.split())


def _matches(value: str, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    return [pattern.pattern for pattern in patterns if pattern.search(value)]


@dataclass(frozen=True)
class ContentFinding:
    code: str
    severity: str
    slide_id: str
    field: str
    message: str
    excerpt: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "slideId": self.slide_id,
            "field": self.field,
            "message": self.message,
            "excerpt": self.excerpt,
        }


def _approved_exception(
    slide_id: str,
    text: str,
    exceptions: dict[str, list[dict[str, str]]],
) -> bool:
    for receipt in exceptions.get(slide_id, []):
        approved_text = _normalized(str(receipt.get("text", "")))
        reason = _normalized(str(receipt.get("reason", "")))
        receipt_hash = str(receipt.get("receiptHash", ""))
        if not approved_text or not reason or len(receipt_hash) != 64:
            continue
        if approved_text == text and receipt_hash == _canonical_hash(
            {"slideId": slide_id, "text": approved_text, "reason": reason}
        ):
            return True
    return False


def evaluate_slide(
    slide: SlidePlan,
    *,
    approved_exceptions: dict[str, list[dict[str, str]]] | None = None,
) -> list[ContentFinding]:
    """Evaluate visible copy while allowing exact, hash-bound risk/TODO receipts."""

    exceptions = approved_exceptions or {}
    findings: list[ContentFinding] = []
    visible = [("title", _normalized(slide.title))]
    visible.extend((f"body[{index}]", _normalized(value)) for index, value in enumerate(slide.body))

    unresolved_count = 0
    author_task_count = 0
    for field, text in visible:
        if not text:
            findings.append(
                ContentFinding(
                    code="CONTENT_EMPTY_VISIBLE_TEXT",
                    severity="blocking",
                    slide_id=slide.slide_id,
                    field=field,
                    message="visible content is empty",
                    excerpt="",
                )
            )
            continue
        if _matches(text, ENGINEERING_TEXT_PATTERNS):
            findings.append(
                ContentFinding(
                    code="CONTENT_ENGINEERING_TEXT_LEAK",
                    severity="blocking",
                    slide_id=slide.slide_id,
                    field=field,
                    message="internal prompt, QA, or engineering copy is visible",
                    excerpt=text[:180],
                )
            )
        if _matches(text, UNRESOLVED_PATTERNS) and not _approved_exception(
            slide.slide_id, text, exceptions
        ):
            unresolved_count += 1
            findings.append(
                ContentFinding(
                    code="CONTENT_UNRESOLVED_PLACEHOLDER",
                    severity="blocking",
                    slide_id=slide.slide_id,
                    field=field,
                    message="unresolved placeholder lacks an approved limitation/TODO receipt",
                    excerpt=text[:180],
                )
            )
        if field.startswith("body") and _matches(text, AUTHOR_TASK_PATTERNS):
            author_task_count += 1

    content_required = slide.role in CONTENT_REQUIRED_ROLES
    body_count = max(len(slide.body), 1)
    if content_required and author_task_count * 2 >= body_count:
        findings.append(
            ContentFinding(
                code="CONTENT_AUTHOR_TASK_DOMINANT",
                severity="blocking",
                slide_id=slide.slide_id,
                field="body",
                message="author instructions dominate a content-required slide",
                excerpt=" | ".join(_normalized(value) for value in slide.body)[:240],
            )
        )
    if content_required and unresolved_count * 2 >= body_count:
        findings.append(
            ContentFinding(
                code="CONTENT_PLACEHOLDER_DOMINANT",
                severity="blocking",
                slide_id=slide.slide_id,
                field="body",
                message="unresolved placeholders dominate a content-required slide",
                excerpt=" | ".join(_normalized(value) for value in slide.body)[:240],
            )
        )
    return findings


def evaluate_deck(
    deck: DeckPlan,
    *,
    stage: str,
    approved_exceptions: dict[str, list[dict[str, str]]] | None = None,
    subject_sha256: str | None = None,
    evidence_map: dict[str, Any] | None = None,
    source_fragments: list[dict[str, Any]] | None = None,
    source_manifest_sha256: str | None = None,
    represented_text: str | None = None,
    representation_verified: bool | None = None,
) -> dict[str, Any]:
    """Return a deterministic report whose subject hash binds every visible field."""

    subject = deck.model_dump(by_alias=True, mode="json")
    subject_hash = subject_sha256 or _canonical_hash(subject)
    lexical_findings = [
        finding
        for slide in deck.slides
        for finding in evaluate_slide(slide, approved_exceptions=approved_exceptions)
    ]
    findings = [item.as_dict() for item in lexical_findings]
    if represented_text is not None:
        visible_representation = _representation_normalized(represented_text)
        represented_engineering = _matches(represented_text, ENGINEERING_TEXT_PATTERNS)
        if represented_engineering:
            findings.append(
                {
                    "code": "CONTENT_ENGINEERING_TEXT_LEAK",
                    "severity": "blocking",
                    "slideId": "deck",
                    "field": "artifact",
                    "message": "artifact contains visible internal authoring instructions",
                    "excerpt": represented_engineering[0][:180],
                }
            )
        for slide in deck.slides:
            for field, value in [
                ("title", slide.title),
                *((f"body[{index}]", item) for index, item in enumerate(slide.body)),
            ]:
                if _representation_normalized(value) not in visible_representation:
                    findings.append(
                        {
                            "code": "CONTENT_REPRESENTATION_MISSING",
                            "severity": "blocking",
                            "slideId": slide.slide_id,
                            "field": field,
                            "message": "approved visible content is missing from this artifact",
                            "excerpt": value[:180],
                        }
                    )
    if representation_verified is False:
        findings.append(
            {
                "code": "CONTENT_REPRESENTATION_UNVERIFIED",
                "severity": "blocking",
                "slideId": "deck",
                "field": "artifact",
                "message": "artifact content representation was not verified",
                "excerpt": stage,
            }
        )
    grounding = None
    if evidence_map is not None:
        if source_fragments is None or source_manifest_sha256 is None:
            raise ValueError("evidence-bound content QA requires sources and manifest hash")
        grounding = evaluate_evidence_map(
            evidence_map,
            source_fragments,
            source_manifest_sha256=source_manifest_sha256,
        )
        findings.extend(grounding["findings"])
    blocking_slide_ids = sorted(
        {
            str(item["slideId"])
            for item in findings
            if item["severity"] == "blocking" and item["slideId"] != "deck"
        }
    )
    passed_slide_count = len(deck.slides) - len(blocking_slide_ids)
    if not findings:
        outcome = "passed"
    elif passed_slide_count:
        outcome = "partially_succeeded"
    else:
        outcome = "needs_manual"
    report = {
        "schema": "instant-ppt.content-quality.v1",
        "stage": stage,
        "subjectSha256": subject_hash,
        "passed": not findings,
        "outcome": outcome,
        "requiredSlideCount": len(deck.slides),
        "passedSlideCount": passed_slide_count,
        "blockingSlideIds": blocking_slide_ids,
        "findings": findings,
        "sourceManifestSha256": source_manifest_sha256,
        "evidenceMapSha256": (
            str(evidence_map.get("evidenceMapSha256")) if evidence_map is not None else None
        ),
        "grounding": grounding,
        "representationVerified": (
            not any(item["code"].startswith("CONTENT_REPRESENTATION_") for item in findings)
            if represented_text is not None or representation_verified is not None
            else None
        ),
        "repairOwner": "content-strategist" if findings else None,
        "recoveryAction": (
            "replace outline tasks/placeholders with audience-ready claims and supported evidence"
            if findings
            else None
        ),
    }
    report["reportSha256"] = _canonical_hash(report)
    return report
