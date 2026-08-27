"""Map immutable product approval snapshots to the Default Agentic v2 request."""

from __future__ import annotations

import os
from typing import Any

from instant_ppt_domain.models import GenerationJobSlide, GenerationSnapshot

from instant_ppt_worker.presentation_agent_tools import AGENT_TOOL_NAMES
from instant_ppt_worker.settings import native_chart_generation_enabled
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
    outline_by_id = {str(value["outlineSlideId"]): value for value in approved_outline}
    total = len(slides)

    def approved_outline_value(slide: GenerationJobSlide) -> dict[str, Any]:
        value = outline_by_id.get(str(slide.outline_slide_id))
        if value is None:
            raise ValueError("generation slide is missing from the approved snapshot outline")
        return value

    def resolved_role(slide: GenerationJobSlide) -> str:
        value = str(approved_outline_value(slide).get("type") or "content")
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
        template.get("descriptorSha256") or template.get("contentSha256") or "0" * 64
    )
    model = str(
        payload.get("providerConfiguration", {}).get("planning", {}).get("model") or "kimi-k3"
    )
    frozen_authoring = dict(payload.get("authoringPolicy") or {})
    authoring_mode = str(frozen_authoring.get("mode") or "deterministic-template")
    if authoring_mode not in {"agent-authoring", "deterministic-template"}:
        raise ValueError("generation snapshot has an invalid authoring mode")
    is_agent_authoring = authoring_mode == "agent-authoring"
    design_authorization = dict(payload.get("designAuthorization") or {})
    if is_agent_authoring and (
        design_authorization.get("authorized") is not True
        or design_authorization.get("scope") != "strategist-design-and-lock"
    ):
        raise ValueError(
            "new Agent workflow requires explicit strategist design/spec-lock authorization"
        )
    fallback_reason = (
        None
        if is_agent_authoring
        else str(
            frozen_authoring.get("fallbackReason") or "legacy-snapshot-without-authoring-policy"
        )
    )
    frozen_visual_review = frozen_authoring.get("visualReview", {})
    visual_review = bool(frozen_visual_review.get("required", False))
    if not is_agent_authoring:
        visual_review = False
    visual_review_max_rounds = int(frozen_visual_review.get("maxRounds", 3 if visual_review else 0))
    if not is_agent_authoring:
        visual_review_max_rounds = 0
    if visual_review_max_rounds < 0 or visual_review_max_rounds > 5:
        raise ValueError("visual review maxRounds must be between zero and five")
    if visual_review and visual_review_max_rounds == 0:
        raise ValueError("required visual review needs at least one review round")
    native_charts = native_chart_generation_enabled()
    planning_configuration = dict(payload.get("providerConfiguration", {}).get("planning") or {})
    image_policy = dict(
        payload.get("imagePolicy") or {"scope": "none", "usage": ["none"], "notes": {}}
    )
    allowed_tools = [
        "read-source",
        "write-project",
        "run-vendored-script",
        "start-live-preview",
    ]
    if is_agent_authoring:
        allowed_tools.extend(
            [
                "provider-text",
                *(tool for tool in AGENT_TOOL_NAMES if native_charts or tool != "run_chart_gate"),
            ]
        )
    if "ai" in list(image_policy.get("usage") or []):
        allowed_tools.append("provider-image")
    return WorkflowRequestV2.model_validate(
        {
            "schemaVersion": 2,
            "workflowRunId": workflow_run_id,
            "organizationId": snapshot.organization_id,
            "route": "generate_pptx",
            "profile": ("default-agentic" if is_agent_authoring else "deterministic-template"),
            "authoring": {
                "mode": authoring_mode,
                "policyVersion": str(
                    frozen_authoring.get("policyVersion") or "presentation-authoring@v1"
                ),
                "fallbackReason": fallback_reason,
                "disclosure": (
                    "agent-authored-editable-draft"
                    if is_agent_authoring
                    else "template-limited-editable-draft"
                ),
                "visualReviewPolicyVersion": str(
                    frozen_authoring.get("visualReview", {}).get("policyVersion")
                    or "visual-review-disabled@v1"
                ),
                "visualReviewRequired": visual_review,
                "visualReviewMaxRounds": visual_review_max_rounds,
            },
            "versions": {
                "workflow": "instant-ppt-default@v3.0.0",
                "engine": "ppt-master@v4.7.0",
                "model": model,
                "prompt": (
                    "default-agentic@v4-strategist-direct-svg"
                    if is_agent_authoring
                    else "deterministic-template@v1"
                ),
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
                    # GenerationJobSlide is mutable runtime state: publication updates its
                    # authored title before the final database transaction. Recovery must
                    # rebuild the immutable request only from the approved snapshot.
                    "title": str(approved_outline_value(slide)["title"]),
                    "audienceQuestion": (
                        "；".join(
                            str(value).strip()
                            for value in outline_by_id.get(str(slide.outline_slide_id), {}).get(
                                "keyPoints", []
                            )
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
                "visualReview": visual_review,
                "refineSpec": False,
                "nativeCharts": native_charts,
            },
            "runtime": {
                "allowedTools": allowed_tools,
                "allowSubagentResearch": False,
                "allowSubagentReview": visual_review,
                "allowSubagentSvgAuthoring": False,
                # Qwen3.8-max medium reasoning uses up to 32K thinking tokens on
                # multimodal calls through the configured gateway. Keep room for
                # the final structured response after the thinking budget.
                "maxCompletionTokensPerTurn": int(
                    os.getenv("PRESENTATION_MAX_COMPLETION_TOKENS_PER_TURN", "40000")
                ),
                "maxTurns": 120,
                # Long decks naturally consume more cumulative tokens. Keep usage observable,
                # while relying on per-turn, turn-count, cost, and timeout guards for safety.
                "maxTokens": None,
                "maxCostMicrounits": 500000,
                "inputCostMicrounitsPer1K": int(
                    planning_configuration.get("inputCostMicrounitsPer1K") or 0
                ),
                "outputCostMicrounitsPer1K": int(
                    planning_configuration.get("outputCostMicrounitsPer1K") or 0
                ),
                "softTimeoutSeconds": 7200,
                "hardTimeoutSeconds": 7500,
                "previewIdleTimeoutSeconds": 9000,
                "maxStageAttempts": 5,
            },
            "confirmation": {
                "mode": "delegated",
                "delegationScope": [
                    "stage1-communication",
                    "free_design",
                    "stage2-production-policy",
                    "strategist-design-and-lock",
                ],
                "policyVersion": "product-autonomy@v1",
                "receiptTtlSeconds": 86400,
            },
            "requestedStage": "attribution_guard",
        }
    )
