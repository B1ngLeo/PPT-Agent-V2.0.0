"""G06 approved-snapshot generation orchestration and immutable publication services."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    Draft,
    Entitlement,
    GenerationArtifact,
    GenerationJob,
    GenerationJobSlide,
    GenerationPublication,
    GenerationSnapshot,
    IdempotencyRecord,
    IntentRevision,
    OutlineApproval,
    OutlineRevision,
    OutlineSlide,
    Presentation,
    PresentationRevision,
    SlideVersion,
    Template,
    TemplateVersion,
    UsageLedger,
    UsageReservation,
)
from instant_ppt_domain.runtime_contract import ENGINE_VERSION, RuntimeIdentity
from instant_ppt_domain.service import (
    CreateJobResult,
    IdempotencyConflict,
    ResourceNotFound,
    _add_task_outbox,
    _advisory_lock,
    _append_event,
    canonical_sha256,
    request_cancel,
    retry_slide,
    serialize_job_snapshot,
)
from instant_ppt_domain.tenancy import TenantContext, append_audit
from instant_ppt_domain.workspace import get_draft

PROMPT_VERSION = "approved-outline-to-deck-plan@2"
FONT_PACK_VERSION = "system-safe-fonts@1"
PROVIDER_CONFIG_VERSION = os.getenv("PROVIDER_CONFIG_VERSION", "deterministic-fake-v1").strip()


def _provider_configuration() -> dict[str, Any]:
    planning_backend = os.getenv("PLANNING_BACKEND", "qwen").strip().lower()
    text_provider = os.getenv("TEXT_PROVIDER", "qwen").strip().lower()
    if not text_provider:
        text_provider = planning_backend if planning_backend in {"kimi", "qwen"} else "qwen"
    if text_provider == "qwen":
        text_configuration = {
            "provider": "qwen",
            "baseUrl": os.getenv(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ).strip(),
            "model": os.getenv("QWEN_MODEL", "qwen3.7-plus").strip(),
            "protocol": "openai",
            "reasoningEffort": os.getenv("QWEN_REASONING_EFFORT", "medium").strip(),
            "enableThinking": os.getenv("QWEN_ENABLE_THINKING", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            "preserveThinking": os.getenv("QWEN_PRESERVE_THINKING", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            "timeoutSeconds": float(os.getenv("QWEN_TIMEOUT_SECONDS", "600")),
            "transportMaxRetries": int(os.getenv("QWEN_TRANSPORT_MAX_RETRIES", "4")),
            "retryBackoffSeconds": float(os.getenv("QWEN_RETRY_BACKOFF_SECONDS", "2")),
            "streaming": os.getenv("QWEN_STREAMING", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            "inputCostMicrounitsPer1K": int(os.getenv("QWEN_INPUT_COST_MICROUNITS_PER_1K", "0")),
            "outputCostMicrounitsPer1K": int(os.getenv("QWEN_OUTPUT_COST_MICROUNITS_PER_1K", "0")),
        }
    elif text_provider == "kimi":
        text_configuration = {
            "provider": "kimi",
            "baseUrl": os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1").strip(),
            "model": os.getenv("KIMI_MODEL", "kimi-k3").strip(),
            "protocol": os.getenv("KIMI_PROTOCOL", "openai").strip().lower(),
            "reasoningEffort": os.getenv("KIMI_REASONING_EFFORT", "max").strip(),
            "timeoutSeconds": float(os.getenv("KIMI_TIMEOUT_SECONDS", "600")),
            "transportMaxRetries": int(os.getenv("KIMI_TRANSPORT_MAX_RETRIES", "4")),
            "retryBackoffSeconds": float(os.getenv("KIMI_RETRY_BACKOFF_SECONDS", "2")),
            "streaming": os.getenv("KIMI_ANTHROPIC_STREAMING", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            "inputCostMicrounitsPer1K": int(os.getenv("KIMI_INPUT_COST_MICROUNITS_PER_1K", "0")),
            "outputCostMicrounitsPer1K": int(os.getenv("KIMI_OUTPUT_COST_MICROUNITS_PER_1K", "0")),
        }
    else:
        raise ValueError("TEXT_PROVIDER must be kimi or qwen")
    return {
        "schemaVersion": 1,
        "planning": {
            "backend": planning_backend,
            **text_configuration,
        },
        "image": {
            "enabled": os.getenv("IMAGE_GENERATION_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            "backend": os.getenv("IMAGE_BACKEND", "openai").strip().lower(),
            "baseUrl": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            "model": os.getenv("OPENAI_MODEL", "gpt-image-2").strip(),
            "outputFormat": os.getenv("OPENAI_OUTPUT_FORMAT", "png").strip().lower(),
            "size": os.getenv("OPENAI_IMAGE_SIZE", "1536x1024").strip(),
            "quality": os.getenv("OPENAI_IMAGE_QUALITY", "low").strip().lower(),
            "maxImagesPerDeck": int(os.getenv("IMAGE_MAX_PER_DECK", "0")),
            "costMicrounitsPerImage": int(os.getenv("IMAGE_COST_MICROUNITS", "100000")),
        },
    }


def _authoring_policy() -> dict[str, Any]:
    mode = os.getenv("PRESENTATION_AUTHORING_MODE", "agent-authoring").strip().lower()
    if mode not in {"agent-authoring", "deterministic-template"}:
        raise ValueError(
            "PRESENTATION_AUTHORING_MODE must be agent-authoring or deterministic-template"
        )
    if mode == "deterministic-template":
        return {
            "schemaVersion": 1,
            "mode": mode,
            "policyVersion": "presentation-authoring@v1",
            "fallbackReason": "operator-feature-flag",
            "visualReview": {
                "required": False,
                "policyVersion": "visual-review-disabled-for-template@v1",
                "maxRounds": 0,
            },
        }
    visual_review_required = os.getenv(
        "PRESENTATION_VISUAL_REVIEW_REQUIRED", "true"
    ).strip().lower() in {"1", "true", "yes", "on"}
    return {
        "schemaVersion": 1,
        "mode": mode,
        "policyVersion": "presentation-authoring@v2-direct-svg",
        "fallbackReason": None,
        "visualReview": {
            "required": visual_review_required,
            "policyVersion": (
                "visual-review-adaptive@v2"
                if visual_review_required
                else "visual-review-operator-disabled@v2"
            ),
            "maxRounds": 5 if visual_review_required else 0,
        },
    }


def _safe_presentation_filename(title: str, authoring_mode: str) -> str:
    safe = "".join(
        "_" if character in '<>:"/\\|?*' or ord(character) < 32 else character
        for character in title.strip()
    ).strip(" .")
    safe = safe[:120] or "AI 演示文稿"
    suffix = "-模板化受限初稿" if authoring_mode == "deterministic-template" else ""
    return f"{safe}{suffix}.pptx"


def _publication_authoring_metadata(
    snapshot: GenerationSnapshot,
    manifest_payload: dict[str, Any],
) -> tuple[dict[str, Any], str, str, str]:
    """Resolve immutable disclosure metadata, including legacy producer fallback."""

    policy = dict(snapshot.payload.get("authoringPolicy") or {})
    authoring = dict(manifest_payload.get("authoring") or {})
    mode = str(authoring.get("mode") or policy.get("mode") or "deterministic-template")
    disclosure = str(
        authoring.get("disclosure")
        or (
            "template-limited-editable-draft"
            if mode == "deterministic-template"
            else "agent-authored-editable-draft"
        )
    )
    fallback_reason = authoring.get("fallbackReason")
    if fallback_reason is None:
        fallback_reason = policy.get("fallbackReason")
    if not authoring:
        authoring = {
            "policyVersion": policy.get("policyVersion", "presentation-authoring@v1"),
            "mode": mode,
            "profile": manifest_payload.get("engineProfile")
            or snapshot.payload.get("engineProfile"),
            "disclosure": disclosure,
            "fallbackReason": fallback_reason,
        }
    title = str(snapshot.payload.get("intent", {}).get("title") or "AI 演示文稿")
    suggested_filename = str(
        manifest_payload.get("suggestedFilename") or _safe_presentation_filename(title, mode)
    )
    return authoring, mode, disclosure, suggested_filename


class GenerationApprovalRequired(ValueError):
    pass


class GenerationTemplateUnavailable(ValueError):
    pass


class GenerationSourceDecisionRequired(ValueError):
    pass


class GenerationQuotaExceeded(ValueError):
    pass


class GenerationCancellationObserved(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CreateApprovedJobCommand:
    context: TenantContext
    draft_id: str
    idempotency_key: str
    request_body: dict[str, Any]
    request_id: str
    failure_modes: dict[int, str] = field(default_factory=dict)
    step_delay_ms: int = 0
    crash_once_at_position: int | None = None
    continue_limited_draft: bool = False
    authorize_strategist_design_lock: bool = False
    image_policy: dict[str, Any] = field(
        default_factory=lambda: {"scope": "none", "usage": ["none"], "notes": {}}
    )


@dataclass(frozen=True, slots=True)
class PublishedArtifactSpec:
    artifact_id: str
    kind: str
    object_key: str
    sha256: str
    media_type: str
    size_bytes: int
    slide_id: str | None = None


def _month_start(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def _check_quota(
    session: Session,
    organization_id: str,
    *,
    slide_count: int,
    image_count: int,
    image_cost_microunits: int,
) -> Entitlement:
    now = datetime.now(UTC)
    entitlement = session.scalar(
        select(Entitlement).where(
            Entitlement.organization_id == organization_id,
            Entitlement.effective_from <= now,
            (Entitlement.effective_until.is_(None) | (Entitlement.effective_until > now)),
        )
    )
    if entitlement is None:
        raise GenerationQuotaExceeded("generation entitlement is unavailable")
    if "native" not in entitlement.allowed_modes:
        raise GenerationQuotaExceeded("native generation mode is not entitled")
    if slide_count > entitlement.max_slides_per_deck:
        raise GenerationQuotaExceeded("slide count exceeds the per-deck entitlement")
    if image_count > entitlement.max_images_per_deck:
        raise GenerationQuotaExceeded("image count exceeds the per-deck entitlement")
    active_jobs = session.scalar(
        select(func.count(GenerationJob.id)).where(
            GenerationJob.organization_id == organization_id,
            GenerationJob.status.in_(("queued", "running", "cancel_requested")),
        )
    )
    if int(active_jobs or 0) >= entitlement.max_concurrent_jobs:
        raise GenerationQuotaExceeded("concurrent generation limit reached")
    settled = session.scalar(
        select(func.coalesce(func.sum(UsageLedger.quantity), 0)).where(
            UsageLedger.organization_id == organization_id,
            UsageLedger.metric == "slides",
            UsageLedger.occurred_at >= _month_start(now),
        )
    )
    reserved_slides = session.scalar(
        select(func.coalesce(func.sum(UsageReservation.reserved_units), 0)).where(
            UsageReservation.organization_id == organization_id,
            UsageReservation.status == "reserved",
        )
    )
    if (
        int(settled or 0) + int(reserved_slides or 0) + slide_count
        > entitlement.monthly_slide_limit
    ):
        raise GenerationQuotaExceeded("monthly slide entitlement would be exceeded")
    settled_images = session.scalar(
        select(func.coalesce(func.sum(UsageLedger.quantity), 0)).where(
            UsageLedger.organization_id == organization_id,
            UsageLedger.metric == "images",
            UsageLedger.occurred_at >= _month_start(now),
        )
    )
    reserved_images = session.scalar(
        select(func.coalesce(func.sum(UsageReservation.reserved_images), 0)).where(
            UsageReservation.organization_id == organization_id,
            UsageReservation.status == "reserved",
        )
    )
    if (
        int(settled_images or 0) + int(reserved_images or 0) + image_count
        > entitlement.monthly_image_limit
    ):
        raise GenerationQuotaExceeded("monthly image entitlement would be exceeded")
    settled_image_cost = session.scalar(
        select(func.coalesce(func.sum(UsageLedger.quantity), 0)).where(
            UsageLedger.organization_id == organization_id,
            UsageLedger.metric == "image_cost_microunits",
            UsageLedger.occurred_at >= _month_start(now),
        )
    )
    reserved_image_cost = session.scalar(
        select(func.coalesce(func.sum(UsageReservation.reserved_cost_microunits), 0)).where(
            UsageReservation.organization_id == organization_id,
            UsageReservation.status == "reserved",
        )
    )
    if (
        int(settled_image_cost or 0) + int(reserved_image_cost or 0) + image_cost_microunits
        > entitlement.monthly_image_cost_limit_microunits
    ):
        raise GenerationQuotaExceeded("monthly image cost entitlement would be exceeded")
    return entitlement


def _approved_inputs(
    session: Session, draft: Draft
) -> tuple[OutlineApproval, IntentRevision, OutlineRevision, list[OutlineSlide], TemplateVersion]:
    if not draft.approved_outline_revision_id:
        raise GenerationApprovalRequired("an approved outline revision is required")
    approval = session.scalar(
        select(OutlineApproval).where(
            OutlineApproval.organization_id == draft.organization_id,
            OutlineApproval.draft_id == draft.id,
            OutlineApproval.outline_revision_id == draft.approved_outline_revision_id,
        )
    )
    if approval is None:
        raise GenerationApprovalRequired("the approved outline snapshot is unavailable")
    intent = session.scalar(
        select(IntentRevision).where(
            IntentRevision.id == approval.intent_revision_id,
            IntentRevision.organization_id == draft.organization_id,
        )
    )
    outline = session.scalar(
        select(OutlineRevision).where(
            OutlineRevision.id == approval.outline_revision_id,
            OutlineRevision.organization_id == draft.organization_id,
        )
    )
    slides = list(
        session.scalars(
            select(OutlineSlide)
            .where(
                OutlineSlide.outline_revision_id == approval.outline_revision_id,
                OutlineSlide.organization_id == draft.organization_id,
            )
            .order_by(OutlineSlide.position)
        )
    )
    template = session.scalar(
        select(TemplateVersion)
        .join(Template, Template.id == TemplateVersion.template_id)
        .where(
            TemplateVersion.id == approval.template_version_id,
            Template.is_active.is_(True),
            TemplateVersion.mode == "native",
        )
    )
    if intent is None or outline is None or not slides:
        raise GenerationApprovalRequired("approved revision inputs are incomplete")
    if template is None:
        raise GenerationTemplateUnavailable("approved template version is unavailable")
    return approval, intent, outline, slides, template


def create_approved_generation_job(
    session: Session, command: CreateApprovedJobCommand
) -> CreateJobResult:
    if not command.idempotency_key or len(command.idempotency_key) > 200:
        raise ValueError("Idempotency-Key must contain 1 to 200 characters")
    route = f"POST /v1/drafts/{command.draft_id}/generation-jobs"
    request_sha = canonical_sha256(command.request_body)
    context = command.context
    _advisory_lock(
        session,
        f"{context.organization_id}:{context.user_id}:{route}:{command.idempotency_key}",
    )
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == context.organization_id,
            IdempotencyRecord.actor_id == context.user_id,
            IdempotencyRecord.route == route,
            IdempotencyRecord.idempotency_key == command.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_sha256 != request_sha:
            raise IdempotencyConflict("Idempotency-Key was already used with a different body")
        return CreateJobResult(
            job_id=existing.resource_id,
            status_code=existing.response_status,
            headers={str(key): str(value) for key, value in existing.response_headers.items()},
            body=existing.response_body,
            replayed=True,
        )

    draft = get_draft(session, command.draft_id, context.organization_id, for_update=True)
    if not command.authorize_strategist_design_lock:
        raise GenerationApprovalRequired(
            "Strategist design and spec-lock authorization is required"
        )
    approval, intent, outline, outline_slides, template = _approved_inputs(session, draft)
    has_approved_source = bool(approval.source_summary.get("sourceId"))
    if not has_approved_source and not command.continue_limited_draft:
        raise GenerationSourceDecisionRequired(
            "没有已批准来源；请补充来源，或明确选择继续受限通用初稿"
        )
    provider_configuration = _provider_configuration()
    runtime_identity = RuntimeIdentity.from_env()
    requested_image_policy = dict(command.image_policy)
    requested_image_count = (
        len(dict(requested_image_policy.get("notes") or {}))
        if "ai" in list(requested_image_policy.get("usage") or [])
        else 0
    )
    requested_image_cost = requested_image_count * int(
        provider_configuration["image"]["costMicrounitsPerImage"]
    )
    _check_quota(
        session,
        context.organization_id,
        slide_count=len(outline_slides),
        image_count=requested_image_count,
        image_cost_microunits=requested_image_cost,
    )
    now = datetime.now(UTC)
    snapshot_id = new_ulid()
    slide_ids = [new_ulid() for _ in outline_slides]
    source_hashes = sorted(
        {
            value
            for value in [
                str(approval.source_summary.get("sha256") or ""),
                *[
                    str(item.get("sha256") or "")
                    for item in approval.source_summary.get("artifactDescriptors") or []
                ],
            ]
            if len(value) == 64
        }
    )
    engineering_quick = bool(
        command.failure_modes or command.step_delay_ms or command.crash_once_at_position is not None
    )
    authoring_policy = (
        {
            "schemaVersion": 1,
            "mode": "deterministic-template",
            "policyVersion": "engineering-quick@v1",
            "fallbackReason": "engineering-test-controls",
            "visualReview": {
                "required": False,
                "policyVersion": "visual-review-disabled-for-quick@v1",
                "maxRounds": 0,
            },
        }
        if engineering_quick
        else _authoring_policy()
    )
    engine_profile = (
        "quick-engineering"
        if engineering_quick
        else (
            "default-agentic"
            if authoring_policy["mode"] == "agent-authoring"
            else "deterministic-template"
        )
    )
    image_scope = str(requested_image_policy.get("scope") or "none")
    image_usage = list(requested_image_policy.get("usage") or ["none"])
    raw_image_notes = dict(requested_image_policy.get("notes") or {})
    outline_to_slide = {
        slide.outline_slide_id: slide_id
        for slide, slide_id in zip(outline_slides, slide_ids, strict=True)
    }
    image_notes = {
        ("cover" if key == "cover" else outline_to_slide.get(str(key), "")): str(value)
        for key, value in raw_image_notes.items()
    }
    if "" in image_notes:
        raise ValueError("image notes must reference an approved outline slide")
    if image_scope == "none":
        image_policy = {"scope": "none", "usage": ["none"], "notes": {}}
    else:
        image_policy = {
            "scope": image_scope,
            "usage": image_usage,
            "notes": image_notes,
            "aiPath": requested_image_policy.get("aiPath"),
            "aiPathChain": list(requested_image_policy.get("aiPathChain") or []),
            "providedAssets": [],
            "officeNativeFallbacks": [],
        }
    template_candidate = {
        "candidateId": template.id,
        "kind": "deck",
        "provenance": "library",
        "workspaceRoot": f"templates/catalog/{template.id}",
        "templateId": template.template_id,
        "engineCompatibility": template.engine_compatibility,
        "contentAccessed": False,
        "installed": False,
    }
    template_candidate["descriptorSha256"] = canonical_sha256(template_candidate)
    snapshot_payload: dict[str, Any] = {
        "schemaVersion": 2,
        "snapshotId": snapshot_id,
        "organizationId": context.organization_id,
        "draftId": draft.id,
        "approvalId": approval.id,
        "approvalInputHash": approval.snapshot_input_hash,
        "approval": {
            "approvedBy": approval.approved_by,
            "approvedAt": approval.approved_at.isoformat().replace("+00:00", "Z"),
        },
        "intentRevisionId": approval.intent_revision_id,
        "intent": intent.payload,
        "outlineRevisionId": approval.outline_revision_id,
        "outline": {
            "storySummary": outline.story_summary,
            "targetSlideCount": outline.target_slide_count,
            "slides": [
                {
                    "slideId": slide_id,
                    "outlineSlideId": slide.outline_slide_id,
                    "position": slide.position,
                    "type": slide.slide_type,
                    "title": slide.title,
                    "keyPoints": slide.key_points,
                    "sourceCitations": slide.source_citations,
                }
                for slide_id, slide in zip(slide_ids, outline_slides, strict=True)
            ],
        },
        "templateVersionId": template.id,
        "templateCandidate": template_candidate,
        "template": template_candidate,
        "modeId": "native",
        "route": "generate_pptx",
        "engineProfile": engine_profile,
        "authoringPolicy": authoring_policy,
        "designAuthorization": {
            "authorized": True,
            "scope": "strategist-design-and-lock",
            "authorizedBy": context.user_id,
            "authorizedAt": now.isoformat().replace("+00:00", "Z"),
        },
        "sourceHashes": source_hashes,
        "sourceSummary": approval.source_summary,
        "sourceDecision": (
            "approved-artifacts" if has_approved_source else "continue-limited-general-draft"
        ),
        "promptVersion": PROMPT_VERSION,
        "engineVersion": ENGINE_VERSION,
        "containerVersion": runtime_identity.container_version,
        "runtimeContractVersion": runtime_identity.runtime_contract_version,
        "workflowContractVersion": runtime_identity.workflow_contract_version,
        "fontPackVersion": FONT_PACK_VERSION,
        "providerConfigVersion": PROVIDER_CONFIG_VERSION,
        "providerConfiguration": provider_configuration,
        "imagePolicy": image_policy,
        "createdAt": now.isoformat().replace("+00:00", "Z"),
    }
    snapshot_sha = canonical_sha256(snapshot_payload)
    snapshot_payload["snapshotSha256"] = snapshot_sha
    snapshot = GenerationSnapshot(
        id=snapshot_id,
        organization_id=context.organization_id,
        draft_id=draft.id,
        approval_id=approval.id,
        intent_revision_id=approval.intent_revision_id,
        outline_revision_id=approval.outline_revision_id,
        template_version_id=template.id,
        mode_id="native",
        source_hashes=source_hashes,
        prompt_version=PROMPT_VERSION,
        engine_version=ENGINE_VERSION,
        container_version=runtime_identity.container_version,
        font_pack_version=FONT_PACK_VERSION,
        provider_config_version=PROVIDER_CONFIG_VERSION,
        snapshot_sha256=snapshot_sha,
        payload=snapshot_payload,
        created_at=now,
        updated_at=now,
    )
    session.add(snapshot)
    session.flush()
    job = GenerationJob(
        id=new_ulid(),
        organization_id=context.organization_id,
        snapshot_id=snapshot.id,
        processor="real",
        status="queued",
        stage="deck_planning",
        latest_seq=0,
        attempt=0,
        publication_version=0,
        progress_completed=0,
        progress_total=len(outline_slides),
        test_behavior={
            "stepDelayMs": command.step_delay_ms,
            "crashOnceAtPosition": command.crash_once_at_position,
            "crashConsumed": False,
        },
    )
    session.add(job)
    session.flush()
    for slide_id, slide in zip(slide_ids, outline_slides, strict=True):
        session.add(
            GenerationJobSlide(
                id=new_ulid(),
                organization_id=context.organization_id,
                job_id=job.id,
                slide_id=slide_id,
                outline_slide_id=slide.outline_slide_id,
                position=slide.position,
                title=slide.title,
                body=list(slide.key_points),
                status="pending",
                stage="content_generation",
                attempt=0,
                max_attempts=2,
                failure_mode=command.failure_modes.get(slide.position, "none"),
                logical_task_key=(
                    f"{context.organization_id}:{snapshot.id}:slide_generation:{slide_id}"
                ),
            )
        )
    session.add(
        UsageReservation(
            id=new_ulid(),
            organization_id=context.organization_id,
            job_id=job.id,
            status="reserved",
            reserved_units=len(outline_slides),
            settled_units=0,
            reserved_images=requested_image_count,
            settled_images=0,
            reserved_cost_microunits=requested_image_cost,
            settled_cost_microunits=0,
        )
    )
    draft.status = "generating"
    draft.lock_version += 1
    draft.updated_at = now
    _append_event(
        session,
        job,
        "job.queued",
        data={
            "mode": "native",
            "templateVersionId": template.id,
            "approvalId": approval.id,
        },
    )
    _add_task_outbox(session, job, "initial")
    body = {
        "schemaVersion": 1,
        "resourceId": job.id,
        "resourceType": "generationJob",
        "data": serialize_job_snapshot(session, job),
        "nextCursor": None,
    }
    headers = {"Location": f"/v1/jobs/{job.id}"}
    session.add(
        IdempotencyRecord(
            id=new_ulid(),
            organization_id=context.organization_id,
            actor_id=context.user_id,
            actor_kind="user",
            route=route,
            idempotency_key=command.idempotency_key,
            request_sha256=request_sha,
            response_status=202,
            response_headers=headers,
            response_body=body,
            resource_id=job.id,
            expires_at=now + timedelta(days=7),
            created_at=now,
            updated_at=now,
        )
    )
    append_audit(
        session,
        context,
        resource_type="generation_job",
        resource_id=job.id,
        action="generation_job.created_from_approval",
        request_id=command.request_id,
        outcome="succeeded",
        details={"snapshotId": snapshot.id, "approvalId": approval.id},
    )
    return CreateJobResult(
        job_id=job.id,
        status_code=202,
        headers=headers,
        body=body,
        replayed=False,
    )


def get_generation_snapshot(
    session: Session, snapshot_id: str, organization_id: str
) -> GenerationSnapshot:
    snapshot = session.scalar(
        select(GenerationSnapshot).where(
            GenerationSnapshot.id == snapshot_id,
            GenerationSnapshot.organization_id == organization_id,
        )
    )
    if snapshot is None:
        raise ResourceNotFound("generation snapshot does not exist or is not accessible")
    return snapshot


def request_generation_cancel_idempotent(
    session: Session,
    *,
    context: TenantContext,
    job_id: str,
    idempotency_key: str,
    request_body: dict[str, Any],
    request_id: str,
) -> CreateJobResult:
    route = f"POST /v1/jobs/{job_id}:cancel"
    request_sha = canonical_sha256(request_body)
    _advisory_lock(
        session,
        f"{context.organization_id}:{context.user_id}:{route}:{idempotency_key}",
    )
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == context.organization_id,
            IdempotencyRecord.actor_id == context.user_id,
            IdempotencyRecord.route == route,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_sha256 != request_sha:
            raise IdempotencyConflict("Idempotency-Key was already used with a different body")
        return CreateJobResult(
            job_id=existing.resource_id,
            status_code=existing.response_status,
            headers={str(key): str(value) for key, value in existing.response_headers.items()},
            body=existing.response_body,
            replayed=True,
        )
    job = request_cancel(session, job_id, context.organization_id)
    body = {
        "schemaVersion": 1,
        "resourceId": job_id,
        "resourceType": "cancelGenerationJob",
        "data": serialize_job_snapshot(session, job),
        "nextCursor": None,
    }
    headers = {"Location": f"/v1/jobs/{job_id}"}
    now = datetime.now(UTC)
    session.add(
        IdempotencyRecord(
            id=new_ulid(),
            organization_id=context.organization_id,
            actor_id=context.user_id,
            actor_kind="user",
            route=route,
            idempotency_key=idempotency_key,
            request_sha256=request_sha,
            response_status=202,
            response_headers=headers,
            response_body=body,
            resource_id=job.id,
            expires_at=now + timedelta(days=7),
        )
    )
    append_audit(
        session,
        context,
        resource_type="generation_job",
        resource_id=job.id,
        action="generation_job.cancel.requested",
        request_id=request_id,
        outcome="succeeded",
    )
    return CreateJobResult(
        job_id=job.id,
        status_code=202,
        headers=headers,
        body=body,
        replayed=False,
    )


def retry_generation_slide_idempotent(
    session: Session,
    *,
    context: TenantContext,
    job_id: str,
    slide_id: str,
    idempotency_key: str,
    request_body: dict[str, Any],
    request_id: str,
) -> CreateJobResult:
    route = f"POST /v1/jobs/{job_id}/slides/{slide_id}:retry"
    request_sha = canonical_sha256(request_body)
    _advisory_lock(
        session,
        f"{context.organization_id}:{context.user_id}:{route}:{idempotency_key}",
    )
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == context.organization_id,
            IdempotencyRecord.actor_id == context.user_id,
            IdempotencyRecord.route == route,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_sha256 != request_sha:
            raise IdempotencyConflict("Idempotency-Key was already used with a different body")
        return CreateJobResult(
            job_id=job_id,
            status_code=existing.response_status,
            headers={str(key): str(value) for key, value in existing.response_headers.items()},
            body=existing.response_body,
            replayed=True,
        )
    slide = retry_slide(session, job_id, slide_id, context.organization_id)
    body = {
        "schemaVersion": 1,
        "resourceId": slide.slide_id,
        "resourceType": "generationJobSlide",
        "data": {"status": slide.status, "attempt": slide.attempt},
        "nextCursor": None,
    }
    headers = {"Location": f"/v1/jobs/{job_id}"}
    now = datetime.now(UTC)
    session.add(
        IdempotencyRecord(
            id=new_ulid(),
            organization_id=context.organization_id,
            actor_id=context.user_id,
            actor_kind="user",
            route=route,
            idempotency_key=idempotency_key,
            request_sha256=request_sha,
            response_status=202,
            response_headers=headers,
            response_body=body,
            resource_id=slide.slide_id,
            expires_at=now + timedelta(days=7),
        )
    )
    append_audit(
        session,
        context,
        resource_type="generation_job_slide",
        resource_id=slide.slide_id,
        action="generation_slide.retry.requested",
        request_id=request_id,
        outcome="succeeded",
    )
    return CreateJobResult(
        job_id=job_id,
        status_code=202,
        headers=headers,
        body=body,
        replayed=False,
    )


def next_publication_version(session: Session, job_id: str, organization_id: str) -> int:
    job = session.scalar(
        select(GenerationJob).where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == organization_id,
        )
    )
    if job is None:
        raise ResourceNotFound("generation job does not exist or is not accessible")
    return job.publication_version + 1


def _settle_usage(
    session: Session,
    job: GenerationJob,
    *,
    ready_count: int,
    worker_seconds: int,
    publication_version: int,
    image_count: int = 0,
    image_cost_microunits: int = 0,
    model_tokens: int = 0,
    model_cost_microunits: int = 0,
) -> None:
    reservation = session.scalar(
        select(UsageReservation).where(UsageReservation.job_id == job.id).with_for_update()
    )
    if reservation is not None and reservation.status in {"reserved", "settled"}:
        reservation.status = "settled"
        reservation.settled_units = max(reservation.settled_units, ready_count)
        reservation.settled_images = max(reservation.settled_images, image_count)
        reservation.settled_cost_microunits = max(
            reservation.settled_cost_microunits,
            image_cost_microunits,
        )
    now = datetime.now(UTC)
    previously_billed_slides = int(
        session.scalar(
            select(func.coalesce(func.sum(UsageLedger.quantity), 0)).where(
                UsageLedger.organization_id == job.organization_id,
                UsageLedger.job_id == job.id,
                UsageLedger.metric == "slides",
            )
        )
        or 0
    )
    metrics = {
        "slides": max(0, ready_count - previously_billed_slides),
        "model_tokens": max(0, model_tokens),
        "model_cost_microunits": max(0, model_cost_microunits),
        "images": max(0, image_count),
        "image_cost_microunits": max(0, image_cost_microunits),
        "worker_seconds": max(0, worker_seconds),
    }
    for metric, quantity in metrics.items():
        dedupe_key = f"generation:{job.id}:v{publication_version}:{metric}"
        if session.scalar(
            select(UsageLedger.id).where(
                UsageLedger.organization_id == job.organization_id,
                UsageLedger.dedupe_key == dedupe_key,
            )
        ):
            continue
        session.add(
            UsageLedger(
                id=new_ulid(),
                organization_id=job.organization_id,
                job_id=job.id,
                metric=metric,
                quantity=quantity,
                dedupe_key=dedupe_key,
                details={"processor": job.processor, "publicationVersion": publication_version},
                occurred_at=now,
            )
        )


def publish_generation_result(
    session: Session,
    *,
    job_id: str,
    organization_id: str,
    worker_id: str,
    publication_version: int,
    artifacts: list[PublishedArtifactSpec],
    manifest_artifact_id: str,
    manifest_payload: dict[str, Any],
    presentation_id: str,
    presentation_revision_id: str,
    worker_seconds: int,
) -> tuple[GenerationPublication, Presentation, PresentationRevision]:
    job = session.scalar(
        select(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == organization_id,
        )
        .with_for_update()
    )
    if job is None:
        raise ResourceNotFound("generation job does not exist or is not accessible")
    if job.lease_owner != worker_id:
        raise RuntimeError("worker does not own the generation job lease")
    if job.processor != "real":
        raise ValueError("real generation publication requires a real processor job")
    if job.status == "cancel_requested":
        raise GenerationCancellationObserved("cancellation won the publication race")
    existing = session.scalar(
        select(GenerationPublication).where(
            GenerationPublication.job_id == job.id,
            GenerationPublication.version == publication_version,
        )
    )
    if existing is not None:
        presentation = session.scalar(
            select(Presentation).where(Presentation.generation_job_id == job.id)
        )
        revision = (
            session.get(PresentationRevision, presentation.current_revision_id)
            if presentation and presentation.current_revision_id
            else None
        )
        if presentation is None or revision is None:
            raise RuntimeError("published generation is missing its presentation revision")
        return existing, presentation, revision

    if publication_version != job.publication_version + 1:
        raise RuntimeError("generation publication version is stale")
    slides = list(
        session.scalars(
            select(GenerationJobSlide)
            .where(GenerationJobSlide.job_id == job.id)
            .order_by(GenerationJobSlide.position)
            .with_for_update()
        )
    )
    ready_count = sum(slide.status == "ready" for slide in slides)
    failed_count = sum(slide.status == "failed" for slide in slides)
    if any(slide.status not in {"ready", "failed"} for slide in slides) or ready_count == 0:
        raise RuntimeError("generation cannot publish before slide processing is complete")
    target = "succeeded" if failed_count == 0 else "partially_succeeded"
    artifact_by_slide: dict[str, str] = {}
    presentation = session.scalar(
        select(Presentation).where(Presentation.generation_job_id == job.id).with_for_update()
    )
    if presentation is not None and presentation.current_revision_id:
        prior_slides = list(
            session.scalars(
                select(SlideVersion).where(
                    SlideVersion.presentation_revision_id == presentation.current_revision_id,
                    SlideVersion.organization_id == organization_id,
                    SlideVersion.status == "ready",
                    SlideVersion.artifact_id.is_not(None),
                )
            )
        )
        artifact_by_slide.update(
            {
                slide.slide_id: slide.artifact_id
                for slide in prior_slides
                if slide.artifact_id is not None
            }
        )
    now = datetime.now(UTC)
    for item in artifacts:
        session.add(
            Artifact(
                id=item.artifact_id,
                organization_id=organization_id,
                artifact_type=item.kind,
                partition="published",
                object_key=item.object_key,
                sha256=item.sha256,
                media_type=item.media_type,
                size_bytes=item.size_bytes,
                status="published",
                retention_expires_at=now + timedelta(days=30),
            )
        )
        session.add(
            GenerationArtifact(
                id=new_ulid(),
                organization_id=organization_id,
                job_id=job.id,
                artifact_id=item.artifact_id,
                kind=item.kind,
                slide_id=item.slide_id,
                publication_version=publication_version,
            )
        )
        if item.kind == "generation_slide_svg" and item.slide_id:
            artifact_by_slide[item.slide_id] = item.artifact_id
    session.flush()
    manifest_spec = next(
        (item for item in artifacts if item.artifact_id == manifest_artifact_id), None
    )
    if manifest_spec is None or manifest_spec.kind != "generation_manifest":
        raise RuntimeError("generation manifest artifact is missing from publication")
    manifest_sha = manifest_spec.sha256
    publication = GenerationPublication(
        id=new_ulid(),
        organization_id=organization_id,
        job_id=job.id,
        version=publication_version,
        manifest_artifact_id=manifest_artifact_id,
        manifest_sha256=manifest_sha,
        payload=manifest_payload,
    )
    session.add(publication)
    snapshot = session.get(GenerationSnapshot, job.snapshot_id)
    if snapshot is None:
        raise RuntimeError("generation snapshot disappeared during publication")
    authoring, authoring_mode, authoring_disclosure, suggested_filename = (
        _publication_authoring_metadata(snapshot, manifest_payload)
    )
    if presentation is None:
        presentation = Presentation(
            id=presentation_id,
            organization_id=organization_id,
            draft_id=snapshot.draft_id,
            generation_job_id=job.id,
            title=str(snapshot.payload.get("intent", {}).get("title") or "AI 演示文稿"),
            status="ready" if target == "succeeded" else "partial",
            lock_version=1,
        )
        session.add(presentation)
        session.flush()
        revision_number = 1
    else:
        if presentation.id != presentation_id:
            raise RuntimeError("generation presentation identity is not deterministic")
        revision_number = (
            int(
                session.scalar(
                    select(func.coalesce(func.max(PresentationRevision.revision_number), 0)).where(
                        PresentationRevision.presentation_id == presentation.id
                    )
                )
                or 0
            )
            + 1
        )
        presentation.status = "ready" if target == "succeeded" else "partial"
        presentation.lock_version += 1
    revision_id = presentation_revision_id
    revision_payload = {
        "schemaVersion": 1,
        "presentationRevisionId": revision_id,
        "presentationId": presentation.id,
        "generationJobId": job.id,
        "snapshotId": job.snapshot_id,
        "publicationVersion": publication_version,
        "contentMode": manifest_payload.get("contentMode")
        or ("source-grounded" if snapshot.payload.get("sourceHashes") else "limited-general-draft"),
        "engineProfile": manifest_payload.get("engineProfile")
        or snapshot.payload.get("engineProfile"),
        "authoring": authoring,
        "authoringMode": authoring_mode,
        "authoringDisclosure": authoring_disclosure,
        "suggestedFilename": suggested_filename,
        "partial": target == "partially_succeeded",
        "slides": [
            {
                "slideId": slide.slide_id,
                "outlineSlideId": slide.outline_slide_id,
                "position": slide.position,
                "status": slide.status,
                "title": slide.title,
                "body": slide.body,
                "artifactId": artifact_by_slide.get(slide.slide_id),
                "errorCode": slide.error_code,
            }
            for slide in slides
        ],
    }
    revision = PresentationRevision(
        id=revision_id,
        organization_id=organization_id,
        presentation_id=presentation.id,
        generation_job_id=job.id,
        snapshot_id=job.snapshot_id,
        manifest_artifact_id=manifest_artifact_id,
        revision_number=revision_number,
        operation="generation" if revision_number == 1 else "generation_retry",
        partial=target == "partially_succeeded",
        payload=revision_payload,
        payload_sha256=canonical_sha256(revision_payload),
    )
    session.add(revision)
    session.flush()
    for slide in slides:
        slide_payload = {
            "slideId": slide.slide_id,
            "outlineSlideId": slide.outline_slide_id,
            "position": slide.position,
            "status": slide.status,
            "title": slide.title,
            "body": slide.body,
            "artifactId": artifact_by_slide.get(slide.slide_id),
            "errorCode": slide.error_code,
        }
        session.add(
            SlideVersion(
                id=new_ulid(),
                organization_id=organization_id,
                presentation_revision_id=revision.id,
                slide_id=slide.slide_id,
                outline_slide_id=slide.outline_slide_id or slide.slide_id,
                position=slide.position,
                status=slide.status,
                title=slide.title or "未命名页面",
                body=list(slide.body),
                artifact_id=artifact_by_slide.get(slide.slide_id),
                error_code=slide.error_code,
                payload_sha256=canonical_sha256(slide_payload),
            )
        )
    presentation.current_revision_id = revision.id
    job.publication_version = publication_version
    job.status = target
    job.stage = "publishing"
    job.terminal_at = now
    job.lock_version += 1
    draft = session.scalar(
        select(Draft)
        .where(Draft.id == snapshot.draft_id, Draft.organization_id == organization_id)
        .with_for_update()
    )
    if draft is not None:
        draft.status = "completed" if target == "succeeded" else "needs_attention"
        draft.lock_version += 1
        draft.updated_at = now
    _settle_usage(
        session,
        job,
        ready_count=ready_count,
        worker_seconds=worker_seconds,
        publication_version=publication_version,
        image_count=sum(
            item.kind in {"generation_ai_cover_image", "generation_image_asset"}
            for item in artifacts
        ),
        image_cost_microunits=int(
            manifest_payload.get("imageGeneration", {}).get("costMicrounits") or 0
        ),
        model_tokens=(
            int(manifest_payload.get("authoring", {}).get("usage", {}).get("inputTokens") or 0)
            + int(manifest_payload.get("authoring", {}).get("usage", {}).get("outputTokens") or 0)
        ),
        model_cost_microunits=int(
            manifest_payload.get("authoring", {}).get("usage", {}).get("costMicrounits") or 0
        ),
    )
    _append_event(
        session,
        job,
        "artifact.published",
        data={
            "publicationId": publication.id,
            "manifestArtifactId": manifest_artifact_id,
            "presentationId": presentation.id,
            "presentationRevisionId": revision.id,
        },
    )
    _append_event(
        session,
        job,
        "job.completed" if target == "succeeded" else "job.partially_completed",
        data={
            "presentationId": presentation.id,
            "presentationRevisionId": revision.id,
            "engineProfile": manifest_payload.get("engineProfile"),
            "authoringMode": (manifest_payload.get("authoring") or {}).get("mode"),
            "authoringDisclosure": (manifest_payload.get("authoring") or {}).get("disclosure"),
            "fallbackReason": (manifest_payload.get("authoring") or {}).get("fallbackReason"),
        },
    )
    return publication, presentation, revision


def cancel_generation_job(
    session: Session,
    *,
    job_id: str,
    organization_id: str,
    worker_id: str,
    worker_seconds: int,
) -> GenerationJob:
    """Finalize a requested cancellation without publishing a presentation."""

    job = session.scalar(
        select(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == organization_id,
        )
        .with_for_update()
    )
    if job is None:
        raise ResourceNotFound("generation job does not exist or is not accessible")
    if job.lease_owner != worker_id:
        raise RuntimeError("worker does not own the generation job lease")
    if job.status == "cancelled":
        return job
    if job.status != "cancel_requested":
        raise RuntimeError("generation job has not requested cancellation")
    slides = list(
        session.scalars(
            select(GenerationJobSlide).where(GenerationJobSlide.job_id == job.id).with_for_update()
        )
    )
    for slide in slides:
        if slide.status in {"pending", "running", "retrying"}:
            slide.status = "cancelled"
            slide.lock_version += 1
    ready_count = sum(slide.status == "ready" for slide in slides)
    next_version = job.publication_version + 1
    _settle_usage(
        session,
        job,
        ready_count=ready_count,
        worker_seconds=worker_seconds,
        publication_version=next_version,
    )
    if ready_count == 0:
        reservation = session.scalar(
            select(UsageReservation).where(UsageReservation.job_id == job.id).with_for_update()
        )
        if reservation is not None:
            reservation.status = "released"
    now = datetime.now(UTC)
    job.status = "cancelled"
    job.terminal_at = now
    job.lock_version += 1
    snapshot = session.get(GenerationSnapshot, job.snapshot_id)
    if snapshot is not None:
        draft = session.scalar(
            select(Draft)
            .where(Draft.id == snapshot.draft_id, Draft.organization_id == organization_id)
            .with_for_update()
        )
        if draft is not None:
            draft.status = "cancelled"
            draft.lock_version += 1
            draft.updated_at = now
    _append_event(
        session,
        job,
        "job.cancelled",
        data={"readySlideCount": ready_count, "published": False},
    )
    return job


def record_compiled_slides(
    session: Session,
    *,
    job_id: str,
    organization_id: str,
    worker_id: str,
    compiled: dict[str, tuple[str, dict[str, Any]]],
) -> None:
    """Bind final-deck SVG hashes and QA evidence to already-ready slide tasks."""

    job = session.scalar(
        select(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == organization_id,
        )
        .with_for_update()
    )
    if job is None:
        raise ResourceNotFound("generation job does not exist or is not accessible")
    if job.lease_owner != worker_id:
        raise RuntimeError("worker does not own the generation job lease")
    slides = list(
        session.scalars(
            select(GenerationJobSlide).where(GenerationJobSlide.job_id == job.id).with_for_update()
        )
    )
    for slide in slides:
        if slide.status != "ready":
            continue
        evidence = compiled.get(slide.slide_id)
        if evidence is None:
            raise RuntimeError(f"compiled SVG is missing for ready slide {slide.slide_id}")
        render_sha, qa_report = evidence
        slide.render_sha256 = render_sha
        slide.qa_report = qa_report
        slide.lock_version += 1


def fail_generation_job(
    session: Session,
    *,
    job_id: str,
    organization_id: str,
    worker_id: str,
    error_code: str,
    worker_seconds: int,
) -> GenerationJob:
    job = session.scalar(
        select(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == organization_id,
        )
        .with_for_update()
    )
    if job is None:
        raise ResourceNotFound("generation job does not exist or is not accessible")
    if job.lease_owner != worker_id:
        raise RuntimeError("worker does not own the generation job lease")
    if job.status in {"succeeded", "partially_succeeded", "failed", "cancelled"}:
        return job
    slides = list(
        session.scalars(select(GenerationJobSlide).where(GenerationJobSlide.job_id == job.id))
    )
    ready_count = sum(slide.status == "ready" for slide in slides)
    job.status = "failed"
    job.terminal_at = datetime.now(UTC)
    job.lock_version += 1
    snapshot = session.get(GenerationSnapshot, job.snapshot_id)
    if snapshot is not None:
        draft = session.scalar(
            select(Draft)
            .where(Draft.id == snapshot.draft_id, Draft.organization_id == organization_id)
            .with_for_update()
        )
        if draft is not None:
            draft.status = "failed"
            draft.lock_version += 1
    _settle_usage(
        session,
        job,
        ready_count=ready_count,
        worker_seconds=worker_seconds,
        publication_version=job.publication_version + 1,
    )
    _append_event(
        session,
        job,
        "job.failed",
        data={"errorCode": error_code, "retryable": False},
    )
    return job
