"""Map immutable product approval snapshots to the Default Agentic v2 request."""

from __future__ import annotations

from typing import Any

from instant_ppt_domain.models import GenerationJobSlide, GenerationSnapshot

from instant_ppt_worker.workflow_models import WorkflowRequestV2


def build_default_workflow_request(
    snapshot: GenerationSnapshot,
    slides: list[GenerationJobSlide],
    *,
    workflow_run_id: str,
    sources: dict[str, Any],
) -> WorkflowRequestV2:
    payload = snapshot.payload
    intent = dict(payload.get("intent") or {})
    approved_outline = list(payload.get("outline", {}).get("slides") or [])
    outline_by_id = {
        str(value["outlineSlideId"]): value for value in approved_outline
    }
    total = len(slides)

    def resolved_role(slide: GenerationJobSlide) -> str:
        value = str(outline_by_id.get(str(slide.outline_slide_id), {}).get("type") or "content")
        normalized = value.lower()
        if slide.position == 1:
            return "cover"
        if slide.position == total:
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
        }.get(normalized, "content")

    template = dict(payload.get("templateCandidate") or payload.get("template") or {})
    candidate_hash = str(
        template.get("descriptorSha256")
        or template.get("contentSha256")
        or "0" * 64
    )
    model = str(
        payload.get("providerConfiguration", {}).get("planning", {}).get("model")
        or "fake"
    )
    image_policy = dict(
        payload.get("imagePolicy")
        or {"scope": "none", "usage": ["none"], "notes": {}}
    )
    allowed_tools = [
        "read-source",
        "write-project",
        "run-vendored-script",
        "start-live-preview",
        "provider-text",
    ]
    if "ai" in list(image_policy.get("usage") or []):
        allowed_tools.append("provider-image")
    return WorkflowRequestV2.model_validate(
        {
            "schemaVersion": 2,
            "workflowRunId": workflow_run_id,
            "organizationId": snapshot.organization_id,
            "route": "generate_pptx",
            "profile": "default-agentic",
            "versions": {
                "workflow": "instant-ppt-default@v2.0.0",
                "engine": "ppt-master@v4.7.0",
                "model": model,
                "prompt": "default-agentic@v1",
                "reference": "ppt-master-default@v4.7.0",
                "adapter": "engine-adapter@v2",
            },
            "approval": {
                "snapshotId": snapshot.id,
                "snapshotSha256": snapshot.snapshot_sha256,
                "intentRevisionId": snapshot.intent_revision_id,
                "outlineRevisionId": snapshot.outline_revision_id,
                "approvalId": snapshot.approval_id,
                "approvedBy": payload["approval"]["approvedBy"],
                "approvedAt": payload["approval"]["approvedAt"],
            },
            "intent": {
                "title": str(intent.get("title") or "AI 演示文稿"),
                "objective": str(intent.get("goal") or "形成可执行的沟通结论"),
                "audience": str(intent.get("audience") or "目标受众"),
                "desiredOutcome": str(intent.get("goal") or "形成下一步行动判断"),
                "language": str(intent.get("language") or "zh-CN"),
                "deliveryContext": "网站可编辑初稿",
            },
            "outline": [
                {
                    "outlineSlideId": slide.outline_slide_id,
                    "slideId": slide.slide_id,
                    "pnn": f"P{index:02d}",
                    "order": index,
                    "role": resolved_role(slide),
                    "title": slide.title,
                    "audienceQuestion": (
                        "；".join(
                            str(value).strip()
                            for value in outline_by_id.get(
                                str(slide.outline_slide_id), {}
                            ).get("keyPoints", [])
                            if str(value).strip()
                        )
                        or f"第 {index} 页需要帮助受众回答什么关键问题？"
                    ),
                }
                for index, slide in enumerate(slides, start=1)
            ],
            "sources": sources,
            "template": {
                "mode": "free_design",
                "candidates": [
                    {
                        "candidateId": str(
                            template.get("candidateId") or snapshot.template_version_id
                        ),
                        "kind": "deck",
                        "provenance": "library",
                        "descriptorSha256": candidate_hash,
                        "workspaceRoot": str(
                            template.get("workspaceRoot")
                            or f"templates/catalog/{snapshot.template_version_id}"
                        ),
                        "contentAccessed": False,
                        "installed": False,
                    }
                ],
                "activeTemplateVersion": None,
            },
            "image": image_policy,
            "research": {"mode": "closed_corpus", "allowedDomains": []},
            "production": {
                "proactiveSpeakerNotes": False,
                "proactiveCustomAnimations": False,
                "proactiveNarrationAudio": False,
                "effectiveSpeakerNotes": "disabled",
                "effectiveCustomAnimations": "disabled",
                "effectiveNarrationAudio": "disabled",
                "visualReview": False,
                "refineSpec": False,
            },
            "runtime": {
                "allowedTools": allowed_tools,
                "allowSubagentResearch": False,
                "allowSubagentReview": False,
                "allowSubagentSvgAuthoring": False,
                "maxTurns": 120,
                "maxTokens": 400000,
                "maxCostMicrounits": 500000,
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
