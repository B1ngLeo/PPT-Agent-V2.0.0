"""Replay the frozen ISSUE-003 approval through the real Agent authoring runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from instant_ppt_domain.service import canonical_sha256
from instant_ppt_worker.agentic_workflow import run_default_workflow
from instant_ppt_worker.approved_sources import _markdown_fragments
from instant_ppt_worker.presentation_agent_tools import AGENT_TOOL_NAMES
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.workflow_models import (
    ApprovedSourceArtifact,
    SourceManifest,
    WorkflowRequestV2,
    WorkflowResultV2,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolved_role(value: str, position: int, total: int) -> str:
    if position == 1:
        return "cover"
    if position == total:
        return "ending"
    return {
        "closing": "ending",
        "ending": "ending",
        "section": "section",
        "data": "data",
        "chart": "data",
        "comparison": "comparison",
        "timeline": "timeline",
        "risk": "risk_action",
        "risk_action": "risk_action",
    }.get(value.lower(), "content")


def build_request(snapshot: dict[str, Any], source_path: Path) -> WorkflowRequestV2:
    payload = dict(snapshot["payload"])
    source_summary = dict(payload["sourceSummary"])
    descriptor = next(
        item
        for item in source_summary["artifactDescriptors"]
        if item["kind"] == "markdown"
    )
    actual_source_sha256 = sha256_file(source_path)
    if actual_source_sha256 != descriptor["sha256"]:
        raise RuntimeError("frozen source hash no longer matches the approved descriptor")
    markdown = source_path.read_text(encoding="utf-8")
    source_artifact = ApprovedSourceArtifact(
        source_artifact_id=descriptor["sourceArtifactId"],
        source_id=source_summary["sourceId"],
        organization_id=payload["organizationId"],
        object_sha256=actual_source_sha256,
        media_type=descriptor["mediaType"],
        parsed_at=payload["approval"]["approvedAt"],
        fragments=_markdown_fragments(markdown, descriptor["sourceArtifactId"]),
    )
    manifest_values = {
        "mode": "approved-artifacts",
        "snapshotSha256": snapshot["snapshotSha256"],
        "artifacts": [source_artifact.model_dump(by_alias=True, mode="json")],
    }
    sources = SourceManifest(
        mode="approved-artifacts",
        artifacts=[source_artifact],
        manifest_sha256=canonical_sha256(manifest_values),
        continue_limited_draft=False,
    )
    approved_outline = list(payload["outline"]["slides"])
    workflow_run_id = deterministic_ulid(
        hashlib.sha256(
            f"issue003-after:{snapshot['snapshotId']}:{snapshot['snapshotSha256']}".encode()
        ).hexdigest()
    )
    allowed_tools = [
        "read-source",
        "write-project",
        "run-vendored-script",
        "start-live-preview",
        "provider-text",
        *AGENT_TOOL_NAMES,
    ]
    intent = dict(payload["intent"])
    return WorkflowRequestV2.model_validate(
        {
            "schemaVersion": 2,
            "workflowRunId": workflow_run_id,
            "organizationId": payload["organizationId"],
            "route": "generate_pptx",
            "profile": "default-agentic",
            "authoring": {
                "mode": "agent-authoring",
                "policyVersion": "presentation-authoring@v1",
                "fallbackReason": None,
                "disclosure": "agent-authored-editable-draft",
                "visualReviewPolicyVersion": "visual-review-required@v1",
                "visualReviewRequired": True,
            },
            "versions": {
                "workflow": "instant-ppt-default@v2.0.0",
                "engine": "ppt-master@v4.7.0",
                "model": "fake-agent@v1",
                "prompt": "default-agentic@v2",
                "reference": "ppt-master-default@v4.7.0",
                "adapter": "engine-adapter@v2",
            },
            "approval": {
                "snapshotId": snapshot["snapshotId"],
                "snapshotSha256": snapshot["snapshotSha256"],
                "intentRevisionId": payload["intentRevisionId"],
                "outlineRevisionId": payload["outlineRevisionId"],
                "approvalId": payload["approvalId"],
                "approvedBy": payload["approval"]["approvedBy"],
                "approvedAt": payload["approval"]["approvedAt"],
            },
            "intent": {
                "title": intent["title"],
                "objective": intent["goal"],
                "audience": intent["audience"],
                "desiredOutcome": intent["goal"],
                "language": intent["language"],
                "deliveryContext": "ISSUE-003 冻结输入 before/after 对照",
            },
            "outline": [
                {
                    "outlineSlideId": slide["outlineSlideId"],
                    "slideId": slide["slideId"],
                    "pnn": f"P{index:02d}",
                    "order": index,
                    "role": resolved_role(slide["type"], index, len(approved_outline)),
                    "title": slide["title"],
                    "audienceQuestion": "；".join(slide["keyPoints"]),
                }
                for index, slide in enumerate(approved_outline, start=1)
            ],
            "sources": sources.model_dump(by_alias=True, mode="json"),
            "template": {
                "mode": "free_design",
                "candidates": [],
                "activeTemplateVersion": None,
            },
            "image": {"scope": "none", "usage": ["none"], "notes": {}},
            "research": {"mode": "closed_corpus", "allowedDomains": []},
            "production": {
                "proactiveSpeakerNotes": False,
                "proactiveCustomAnimations": False,
                "proactiveNarrationAudio": False,
                "effectiveSpeakerNotes": "disabled",
                "effectiveCustomAnimations": "disabled",
                "effectiveNarrationAudio": "disabled",
                "visualReview": True,
                "refineSpec": False,
            },
            "runtime": {
                "allowedTools": allowed_tools,
                "allowSubagentResearch": False,
                "allowSubagentReview": True,
                "allowSubagentSvgAuthoring": False,
                "maxTurns": 160,
                "maxTokens": 500000,
                "maxCostMicrounits": 500000,
                "inputCostMicrounitsPer1K": 0,
                "outputCostMicrounitsPer1K": 0,
                "softTimeoutSeconds": 3600,
                "hardTimeoutSeconds": 3900,
                "previewIdleTimeoutSeconds": 7200,
                "maxStageAttempts": 5,
            },
            "confirmation": {
                "mode": "delegated",
                "delegationScope": [
                    "stage1-communication",
                    "free_design",
                    "stage2-production-policy",
                ],
                "policyVersion": "product-autonomy@v1",
                "receiptTtlSeconds": 86400,
            },
            "requestedStage": "attribution_guard",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("docs/evidence/issue003/baseline/before-approved-snapshot.json"),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("docs/evidence/issue003/baseline/before-approved-source.md"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/issue003/after"),
    )
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[2]
    snapshot_path = (repository_root / args.snapshot).resolve()
    source_path = (repository_root / args.source).resolve()
    output_root = (repository_root / args.output).resolve()
    evidence_root = (repository_root / "docs/evidence/issue003").resolve()
    if evidence_root not in output_root.parents:
        raise SystemExit("output must remain inside docs/evidence/issue003")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    if snapshot["snapshotId"] != snapshot["payload"]["snapshotId"]:
        raise RuntimeError("frozen snapshot identity is inconsistent")
    if snapshot["snapshotSha256"] != snapshot["payload"]["snapshotSha256"]:
        raise RuntimeError("frozen snapshot hash is inconsistent")
    request = build_request(snapshot, source_path)
    existing_projects = (
        list(output_root.glob("agent-candidate_ppt169_*"))
        if output_root.is_dir()
        else []
    )
    if existing_projects:
        if len(existing_projects) != 1:
            raise RuntimeError("candidate evidence root has an ambiguous project roster")
        project = existing_projects[0]
        workflow_result = WorkflowResultV2.model_validate_json(
            (project / "workflow-result.json").read_text(encoding="utf-8")
        )
    else:
        if output_root.exists():
            raise RuntimeError("candidate evidence root exists without a resumable project")
        output_root.mkdir(parents=True)
        result = run_default_workflow(
            repository_root,
            output_root / "agent-candidate",
            request,
        )
        workflow_result = result["result"]
        project = next(
            path
            for path in output_root.iterdir()
            if path.is_dir() and path.name.startswith("agent-candidate_ppt169_")
        )
    if workflow_result.status != "succeeded":
        raise RuntimeError(f"Agent candidate did not succeed: {workflow_result.status}")
    canonical_pptx = project / "exports" / "deck.pptx"
    stable_pptx = output_root / "after-agent-authoring.pptx"
    if not stable_pptx.is_file():
        shutil.copyfile(canonical_pptx, stable_pptx)
    turn_count = len(list((project / "agent" / "turns").glob("*.json")))
    tool_call_count = len(list((project / "agent" / "tool-calls").glob("*.json")))
    visual_review_path = project / "validation" / "visual-review.json"
    visual_review = json.loads(visual_review_path.read_text(encoding="utf-8"))
    evidence = {
        "schemaVersion": 1,
        "status": "passed",
        "comparisonAuthority": {
            "snapshotId": snapshot["snapshotId"],
            "snapshotSha256": snapshot["snapshotSha256"],
            "sourceSha256": sha256_file(source_path),
            "slideIds": [slide.slide_id for slide in request.outline],
            "outlineSlideIds": [slide.outline_slide_id for slide in request.outline],
            "pageCount": len(request.outline),
        },
        "candidate": {
            "workflowRunId": request.workflow_run_id,
            "workflowRequestSha256": canonical_sha256(
                request.model_dump(by_alias=True, mode="json")
            ),
            "authoringMode": request.authoring.mode,
            "authoringDisclosure": request.authoring.disclosure,
            "model": request.versions.model,
            "modelDisclosure": (
                "Deterministic local Provider; real Agent turn/tool/reviewer runtime; "
                "no live Kimi credential was available."
            ),
            "pptx": stable_pptx.name,
            "pptxSha256": sha256_file(stable_pptx),
            "pptxSizeBytes": stable_pptx.stat().st_size,
            "project": project.name,
            "workflowStatus": workflow_result.status,
            "workflowStage": workflow_result.stage,
            "turnCount": turn_count,
            "toolCallCount": tool_call_count,
            "usage": workflow_result.usage.model_dump(by_alias=True, mode="json"),
            "visualReviewRound": visual_review["reviewRound"],
            "visualReviewPassed": visual_review["passed"],
            "visualReviewBlockingCount": sum(
                issue["severity"] == "blocking"
                for issue in visual_review.get("issues", [])
            ),
        },
    }
    (output_root / "candidate-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence["candidate"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
