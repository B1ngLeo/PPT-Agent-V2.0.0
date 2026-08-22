"""Versioned Page Blueprint support checks for ISSUE-003."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from instant_ppt_worker.workflow_models import PageBlueprintArtifact, WorkflowRequestV2

_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d+)?|\.\d+)%?")
_ENGLISH_TERM = re.compile(r"[A-Za-z][A-Za-z0-9._-]*")
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_LITERAL = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)+)"
    r"|(?:\d+(?:\.\d+)?\s*(?:%|req/s|tokens?/s|ms|倍|亿元|万元|美元|分)?)",
    re.IGNORECASE,
)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def extract_literal_constraints(value: str) -> list[str]:
    constraints: list[str] = []
    for match in _LITERAL.finditer(value):
        literal = " ".join(match.group(0).split())
        if literal and literal not in constraints:
            constraints.append(literal)
    return constraints[:64]


def semantic_terms(value: str) -> set[str]:
    terms = {match.group(0).casefold() for match in _ENGLISH_TERM.finditer(value)}
    for run in _CJK_RUN.findall(value):
        terms.update(run[index : index + 2] for index in range(max(1, len(run) - 1)))
    return {term for term in terms if term.strip()}


def semantic_support_score(claim: str, evidence: str) -> float:
    normalized_claim = "".join(claim.casefold().split()).strip("。！？.!?")
    normalized_evidence = "".join(evidence.casefold().split())
    if normalized_claim and normalized_claim in normalized_evidence:
        return 1.0
    numbers = {match.group(0).rstrip("%") for match in _NUMBER.finditer(claim)}
    evidence_numbers = {
        match.group(0).rstrip("%") for match in _NUMBER.finditer(evidence)
    }
    if numbers and not numbers.issubset(evidence_numbers):
        return 0.0
    claim_terms = semantic_terms(claim)
    if not claim_terms:
        return 0.0
    return len(claim_terms & semantic_terms(evidence)) / len(claim_terms)


def _chart_is_supported(page: Any, evidence: str) -> bool:
    chart = page.chart_spec
    if chart is None or chart.comparison_baseline != 0:
        return False
    folded = evidence.casefold()
    return (
        chart.context.casefold() in folded
        and chart.unit.casefold() in folded
        and all(
            point.label.casefold() in folded and f"{point.value:g}" in evidence
            for point in chart.values
        )
    )


def validate_page_blueprint(
    artifact: PageBlueprintArtifact,
    request: WorkflowRequestV2,
    fragments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind every Blueprint page and claim to the approved immutable snapshot."""

    findings: list[dict[str, Any]] = []
    fragment_by_id = {str(item["fragmentId"]): item for item in fragments}
    if artifact.workflow_run_id != request.workflow_run_id:
        findings.append(
            {
                "code": "BLUEPRINT_WORKFLOW_RUN_MISMATCH",
                "severity": "blocking",
                "pnn": "deck",
                "message": "Page Blueprint belongs to another workflow run",
            }
        )
    if artifact.approved_snapshot_sha256 != request.approval.snapshot_sha256:
        findings.append(
            {
                "code": "BLUEPRINT_APPROVAL_STALE",
                "severity": "blocking",
                "pnn": "deck",
                "message": "Page Blueprint is not bound to the approved snapshot",
            }
        )
    if len(artifact.pages) != len(request.outline):
        findings.append(
            {
                "code": "BLUEPRINT_ROSTER_LENGTH_MISMATCH",
                "severity": "blocking",
                "pnn": "deck",
                "message": "Page Blueprint changed the approved page count",
            }
        )
    for page, outline in zip(artifact.pages, request.outline, strict=False):
        if (
            page.outline_slide_id != outline.outline_slide_id
            or page.slide_id != outline.slide_id
            or page.pnn != outline.pnn
            or page.order != outline.order
            or page.role != outline.role
        ):
            findings.append(
                {
                    "code": "BLUEPRINT_APPROVED_ROSTER_MISMATCH",
                    "severity": "blocking",
                    "pnn": page.pnn,
                    "message": "Page Blueprint changed an approved stable ID, order, or role",
                }
            )
        missing_refs = [
            reference
            for reference in page.evidence_refs
            if reference not in fragment_by_id
        ]
        if missing_refs:
            findings.append(
                {
                    "code": "BLUEPRINT_EVIDENCE_NOT_APPROVED",
                    "severity": "blocking",
                    "pnn": page.pnn,
                    "message": "Page Blueprint cites unknown or stale source fragments",
                    "evidenceRefs": missing_refs,
                }
            )
        evidence = "\n".join(
            str(fragment_by_id[reference]["text"])
            for reference in page.evidence_refs
            if reference in fragment_by_id
        )
        if page.source_mode == "approved-artifacts" and not missing_refs:
            score = (
                1.0
                if page.chart_spec is not None and _chart_is_supported(page, evidence)
                else semantic_support_score(page.assertion, evidence)
            )
            if score < 0.55:
                findings.append(
                    {
                        "code": "BLUEPRINT_ASSERTION_UNSUPPORTED",
                        "severity": "blocking",
                        "pnn": page.pnn,
                        "message": "assertion is not semantically supported by evidenceRefs",
                        "supportScore": round(score, 4),
                    }
                )
            unsupported_literals = [
                literal
                for literal in page.literal_constraints
                if literal.casefold() not in evidence.casefold()
            ]
            if unsupported_literals:
                findings.append(
                    {
                        "code": "BLUEPRINT_LITERAL_UNSUPPORTED",
                        "severity": "blocking",
                        "pnn": page.pnn,
                        "message": "literal constraints are absent from approved evidence",
                        "literalConstraints": unsupported_literals,
                    }
                )
    payload = artifact.model_dump(by_alias=True, mode="json")
    report = {
        "schema": "instant-ppt.page-blueprint-support.v1",
        "workflowRunId": request.workflow_run_id,
        "approvedSnapshotSha256": request.approval.snapshot_sha256,
        "sourceManifestSha256": request.sources.manifest_sha256,
        "blueprintSha256": canonical_sha256(payload),
        "pageCount": len(artifact.pages),
        "claimSupportPassCount": len(artifact.pages)
        - len(
            {
                str(item.get("pnn"))
                for item in findings
                if item["code"]
                in {
                    "BLUEPRINT_ASSERTION_UNSUPPORTED",
                    "BLUEPRINT_EVIDENCE_NOT_APPROVED",
                    "BLUEPRINT_LITERAL_UNSUPPORTED",
                }
            }
        ),
        "passed": not findings,
        "findings": findings,
    }
    report["reportSha256"] = canonical_sha256(report)
    return report
