"""G05 draft workspace, immutable revision, template, and approval domain services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Draft,
    GenerationJob,
    GenerationSnapshot,
    IntentRevision,
    OutlineApproval,
    OutlineRevision,
    OutlineSlide,
    Presentation,
    ProviderCall,
    Source,
    SourceArtifact,
    Template,
    TemplateVersion,
)
from instant_ppt_domain.service import canonical_sha256
from instant_ppt_domain.tenancy import TenantContext, append_audit

DEFAULT_TEMPLATE_ID = "01ARZ3NDEKTSV4RRFFQ69G5FB4"
DEFAULT_TEMPLATE_VERSION_ID = "01ARZ3NDEKTSV4RRFFQ69G5FB5"

BUILTIN_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "templateId": DEFAULT_TEMPLATE_ID,
        "templateVersionId": DEFAULT_TEMPLATE_VERSION_ID,
        "slug": "editorial-cobalt",
        "name": "编辑部蓝",
        "category": "business",
        "description": "克制的钴蓝编辑网格，适合汇报与策略材料。",
        "sortOrder": 10,
        "themeSpec": {
            "schemaVersion": 1,
            "themeId": "editorial-cobalt",
            "colorTokens": {"primary": "#1746D1", "background": "#F7F3E8"},
            "fontFamilies": ["Noto Sans CJK SC"],
            "aspectRatio": "16:9",
        },
    },
    {
        "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FB6",
        "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FB7",
        "slug": "signal-red",
        "name": "信号红",
        "category": "strategy",
        "description": "高对比标题与数据标记，适合结论先行的策略提案。",
        "sortOrder": 20,
        "themeSpec": {
            "schemaVersion": 1,
            "themeId": "signal-red",
            "colorTokens": {"primary": "#B42318", "background": "#FFF8F0"},
            "fontFamilies": ["Noto Sans CJK SC"],
            "aspectRatio": "16:9",
        },
    },
    {
        "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FB8",
        "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FB9",
        "slug": "field-notes",
        "name": "研究手记",
        "category": "research",
        "description": "温暖纸面与注释式层级，适合培训和研究叙事。",
        "sortOrder": 30,
        "themeSpec": {
            "schemaVersion": 1,
            "themeId": "field-notes",
            "colorTokens": {"primary": "#365314", "background": "#FAF7ED"},
            "fontFamilies": ["Noto Sans CJK SC"],
            "aspectRatio": "16:9",
        },
    },
)


class WorkspaceNotFound(LookupError):
    pass


class WorkspaceConflict(RuntimeError):
    pass


class WorkspaceValidationError(ValueError):
    pass


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def seed_builtin_templates(session: Session) -> None:
    """Idempotently provision the immutable P1 built-in template catalog."""
    for item in BUILTIN_TEMPLATES:
        template = session.get(Template, item["templateId"])
        if template is None:
            template = Template(
                id=item["templateId"],
                slug=item["slug"],
                name=item["name"],
                category=item["category"],
                description=item["description"],
                is_builtin=True,
                is_active=True,
                sort_order=item["sortOrder"],
            )
            session.add(template)
        if session.get(TemplateVersion, item["templateVersionId"]) is None:
            content = {
                "mode": "native",
                "themeSpec": item["themeSpec"],
                "pageRoles": ["cover", "section", "content", "data", "closing"],
                "editableElements": ["text", "shape", "chart", "table"],
                "engineCompatibility": "ppt-master-v4.7.0",
            }
            session.add(
                TemplateVersion(
                    id=item["templateVersionId"],
                    template_id=item["templateId"],
                    version=1,
                    mode="native",
                    theme_spec=item["themeSpec"],
                    page_roles=content["pageRoles"],
                    editable_elements=content["editableElements"],
                    engine_compatibility=content["engineCompatibility"],
                    content_sha256=canonical_sha256(content),
                )
            )
    session.flush()


def _draft_query(draft_id: str, organization_id: str, *, for_update: bool = False) -> Select:
    statement = select(Draft).where(
        Draft.id == draft_id,
        Draft.organization_id == organization_id,
        Draft.deleted_at.is_(None),
    )
    return statement.with_for_update() if for_update else statement


def get_draft(
    session: Session, draft_id: str, organization_id: str, *, for_update: bool = False
) -> Draft:
    row = session.scalar(_draft_query(draft_id, organization_id, for_update=for_update))
    if row is None:
        raise WorkspaceNotFound("draft does not exist or is not accessible")
    return row


def _template_version(session: Session, template_version_id: str) -> TemplateVersion:
    row = session.get(TemplateVersion, template_version_id)
    if row is None:
        raise WorkspaceValidationError("templateVersionId is unavailable")
    template = session.get(Template, row.template_id)
    if template is None or not template.is_active or row.mode != "native":
        raise WorkspaceValidationError("templateVersionId is unavailable for native mode")
    return row


def create_draft(
    session: Session,
    context: TenantContext,
    *,
    topic: str,
    source_id: str | None,
    template_version_id: str | None,
    request_id: str,
) -> Draft:
    normalized_topic = topic.strip()
    if not normalized_topic and not source_id:
        raise WorkspaceValidationError("topic or sourceId is required")
    seed_builtin_templates(session)
    resolved_template = _template_version(
        session, template_version_id or DEFAULT_TEMPLATE_VERSION_ID
    )
    if source_id:
        source = session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.organization_id == context.organization_id,
                Source.status == "parsed",
            )
        )
        if source is None:
            raise WorkspaceValidationError("sourceId must reference a parsed source")
    title = (normalized_topic or "文档演示").splitlines()[0].strip()[:200]
    row = Draft(
        id=new_ulid(),
        organization_id=context.organization_id,
        owner_user_id=context.user_id,
        title=title,
        topic=normalized_topic,
        source_id=source_id,
        mode="native",
        template_version_id=resolved_template.id,
        status="draft",
        lock_version=1,
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        context,
        resource_type="draft",
        resource_id=row.id,
        action="draft.create",
        request_id=request_id,
        outcome="succeeded",
        details={"mode": "native", "hasSource": bool(source_id)},
    )
    return row


def update_draft(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    lock_version: int,
    topic: str | None = None,
    title: str | None = None,
    template_version_id: str | None = None,
    request_id: str,
) -> Draft:
    row = get_draft(session, draft_id, context.organization_id, for_update=True)
    if row.lock_version != lock_version:
        raise WorkspaceConflict("draft changed since it was loaded")
    if topic is not None:
        row.topic = topic.strip()[:1000]
    if title is not None:
        normalized = title.strip()
        if not normalized:
            raise WorkspaceValidationError("title cannot be empty")
        row.title = normalized[:200]
    if template_version_id is not None:
        row.template_version_id = _template_version(session, template_version_id).id
    if not row.topic and not row.source_id:
        raise WorkspaceValidationError("topic or sourceId is required")
    row.lock_version += 1
    row.updated_at = datetime.now(UTC)
    append_audit(
        session,
        context,
        resource_type="draft",
        resource_id=row.id,
        action="draft.autosave",
        request_id=request_id,
        outcome="succeeded",
        details={"lockVersion": row.lock_version},
    )
    session.flush()
    return row


def delete_draft(
    session: Session, context: TenantContext, draft_id: str, *, request_id: str
) -> Draft:
    row = get_draft(session, draft_id, context.organization_id, for_update=True)
    row.status = "deleted"
    row.deleted_at = datetime.now(UTC)
    row.lock_version += 1
    append_audit(
        session,
        context,
        resource_type="draft",
        resource_id=row.id,
        action="draft.delete_requested",
        request_id=request_id,
        outcome="succeeded",
    )
    # Cleanup is asynchronous, but visibility is revoked by deleted_at in this transaction.
    from instant_ppt_domain.presentation import queue_project_cleanup

    queue_project_cleanup(session, context, row, request_id=request_id)
    return row


def _validate_intent(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    audience = str(data.get("audience") or "").strip()
    goal = str(data.get("goal") or "").strip()
    if not title or not audience or not goal:
        raise WorkspaceValidationError("title, audience, and goal are required")
    slide_count = data.get("targetSlideCount")
    if not isinstance(slide_count, int) or not 4 <= slide_count <= 30:
        raise WorkspaceValidationError("targetSlideCount must be between 4 and 30")
    language = data.get("language", "zh-CN")
    if language not in {"zh-CN", "en-US"}:
        raise WorkspaceValidationError("language must be zh-CN or en-US")
    depth = data.get("contentDepth", "balanced")
    if depth not in {"conclusion_first", "balanced", "research"}:
        raise WorkspaceValidationError("contentDepth is invalid")
    visual = data.get("visualPreference", "data_first")
    if visual not in {"data_first", "photo_illustration", "minimal_visual"}:
        raise WorkspaceValidationError("visualPreference is invalid")
    notes = str(data.get("notes") or "")
    if len(notes) > 4000:
        raise WorkspaceValidationError("notes exceeds 4000 characters")
    source_refs = list(data.get("sourceRefs") or [])
    if len(source_refs) != len(set(source_refs)):
        raise WorkspaceValidationError("sourceRefs must be unique")
    return {
        "schemaVersion": 1,
        "title": title,
        "audience": audience,
        "goal": goal,
        "targetSlideCount": slide_count,
        "language": language,
        "contentDepth": depth,
        "visualPreference": visual,
        "notes": notes,
        "sourceRefs": source_refs,
    }


def create_intent_revision(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    data: dict[str, Any],
    based_on_revision_id: str | None,
    actor_kind: str,
    provider_call_id: str | None,
    request_id: str,
) -> IntentRevision:
    draft = get_draft(session, draft_id, context.organization_id, for_update=True)
    if draft.current_intent_revision_id != based_on_revision_id:
        raise WorkspaceConflict("intent base revision is stale")
    payload = _validate_intent(data)
    row = IntentRevision(
        id=new_ulid(),
        organization_id=context.organization_id,
        draft_id=draft.id,
        based_on_revision_id=based_on_revision_id,
        actor_id=context.user_id,
        actor_kind=actor_kind,
        provider_call_id=provider_call_id,
        payload={},
        payload_sha256="",
    )
    row.payload = {**payload, "intentRevisionId": row.id}
    row.payload_sha256 = canonical_sha256(row.payload)
    session.add(row)
    draft.current_intent_revision_id = row.id
    draft.lock_version += 1
    draft.updated_at = datetime.now(UTC)
    append_audit(
        session,
        context,
        resource_type="intent_revision",
        resource_id=row.id,
        action="intent.revise",
        request_id=request_id,
        outcome="succeeded",
        details={"actorKind": actor_kind, "basedOnRevisionId": based_on_revision_id},
    )
    session.flush()
    return row


def get_intent_revision(session: Session, revision_id: str, organization_id: str) -> IntentRevision:
    row = session.scalar(
        select(IntentRevision).where(
            IntentRevision.id == revision_id,
            IntentRevision.organization_id == organization_id,
        )
    )
    if row is None:
        raise WorkspaceNotFound("intent revision does not exist or is not accessible")
    return row


def list_intent_revisions(
    session: Session, draft_id: str, organization_id: str
) -> list[IntentRevision]:
    get_draft(session, draft_id, organization_id)
    return list(
        session.scalars(
            select(IntentRevision)
            .where(
                IntentRevision.draft_id == draft_id,
                IntentRevision.organization_id == organization_id,
            )
            .order_by(IntentRevision.created_at, IntentRevision.id)
        )
    )


def _validate_outline(
    story_summary: str, target_slide_count: int, slides: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    story = story_summary.strip()
    if not story:
        raise WorkspaceValidationError("storySummary is required")
    if not 4 <= target_slide_count <= 30:
        raise WorkspaceValidationError("targetSlideCount must be between 4 and 30")
    if not 1 <= len(slides) <= 30:
        raise WorkspaceValidationError("outline must contain 1 to 30 slides")
    normalized: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for slide in slides:
        slide_id = str(slide.get("outlineSlideId") or "")
        if len(slide_id) != 26 or slide_id in identifiers:
            raise WorkspaceValidationError("outlineSlideId must be a unique ULID")
        identifiers.add(slide_id)
        slide_type = str(slide.get("type") or "").strip()
        title = str(slide.get("title") or "").strip()
        points = [str(point).strip() for point in slide.get("keyPoints") or []]
        if not slide_type or not title or not points or any(not point for point in points):
            raise WorkspaceValidationError("each slide requires type, title, and keyPoints")
        citations = list(slide.get("sourceCitations") or [])
        if len(citations) != len(set(citations)):
            raise WorkspaceValidationError("sourceCitations must be unique")
        normalized.append(
            {
                "outlineSlideId": slide_id,
                "type": slide_type,
                "title": title,
                "keyPoints": points,
                "sourceCitations": citations,
            }
        )
    return story, normalized


def create_outline_revision(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    story_summary: str,
    target_slide_count: int,
    slides: list[dict[str, Any]],
    based_on_revision_id: str | None,
    actor_kind: str,
    operation: str,
    provider_call_id: str | None,
    request_id: str,
) -> OutlineRevision:
    draft = get_draft(session, draft_id, context.organization_id, for_update=True)
    if draft.current_outline_revision_id != based_on_revision_id:
        raise WorkspaceConflict("outline base revision is stale")
    story, normalized_slides = _validate_outline(story_summary, target_slide_count, slides)
    revision_id = new_ulid()
    payload = {
        "schemaVersion": 1,
        "outlineRevisionId": revision_id,
        "storySummary": story,
        "targetSlideCount": target_slide_count,
        "slides": normalized_slides,
    }
    row = OutlineRevision(
        id=revision_id,
        organization_id=context.organization_id,
        draft_id=draft.id,
        based_on_revision_id=based_on_revision_id,
        actor_id=context.user_id,
        actor_kind=actor_kind,
        provider_call_id=provider_call_id,
        operation=operation[:40],
        story_summary=story,
        target_slide_count=target_slide_count,
        payload_sha256=canonical_sha256(payload),
    )
    session.add(row)
    session.flush()
    for position, slide in enumerate(normalized_slides, start=1):
        session.add(
            OutlineSlide(
                id=new_ulid(),
                organization_id=context.organization_id,
                outline_revision_id=row.id,
                outline_slide_id=slide["outlineSlideId"],
                position=position,
                slide_type=slide["type"],
                title=slide["title"],
                key_points=slide["keyPoints"],
                source_citations=slide["sourceCitations"],
            )
        )
    draft.current_outline_revision_id = row.id
    draft.status = "outline_ready"
    draft.lock_version += 1
    draft.updated_at = datetime.now(UTC)
    append_audit(
        session,
        context,
        resource_type="outline_revision",
        resource_id=row.id,
        action="outline.revise",
        request_id=request_id,
        outcome="succeeded",
        details={"actorKind": actor_kind, "operation": operation},
    )
    session.flush()
    return row


def get_outline_revision(
    session: Session, revision_id: str, organization_id: str
) -> OutlineRevision:
    row = session.scalar(
        select(OutlineRevision).where(
            OutlineRevision.id == revision_id,
            OutlineRevision.organization_id == organization_id,
        )
    )
    if row is None:
        raise WorkspaceNotFound("outline revision does not exist or is not accessible")
    return row


def list_outline_revisions(
    session: Session, draft_id: str, organization_id: str
) -> list[OutlineRevision]:
    get_draft(session, draft_id, organization_id)
    return list(
        session.scalars(
            select(OutlineRevision)
            .where(
                OutlineRevision.draft_id == draft_id,
                OutlineRevision.organization_id == organization_id,
            )
            .order_by(OutlineRevision.created_at, OutlineRevision.id)
        )
    )


def _slides_for(session: Session, revision_id: str) -> list[OutlineSlide]:
    return list(
        session.scalars(
            select(OutlineSlide)
            .where(OutlineSlide.outline_revision_id == revision_id)
            .order_by(OutlineSlide.position)
        )
    )


def record_provider_call(
    session: Session,
    context: TenantContext,
    draft_id: str,
    *,
    provider: str,
    model: str,
    purpose: str,
    request_value: dict[str, Any],
    status: str,
    input_tokens: int,
    output_tokens: int,
    repair_count: int,
    started_at: datetime,
    finished_at: datetime,
    error_code: str | None = None,
) -> ProviderCall:
    get_draft(session, draft_id, context.organization_id)
    row = ProviderCall(
        id=new_ulid(),
        organization_id=context.organization_id,
        draft_id=draft_id,
        provider=provider,
        model=model,
        purpose=purpose,
        request_hash=canonical_sha256(request_value),
        status=status,
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        repair_count=repair_count,
        error_code=error_code,
        started_at=started_at,
        finished_at=finished_at,
    )
    session.add(row)
    session.flush()
    return row


def approve_outline(
    session: Session,
    context: TenantContext,
    outline_revision_id: str,
    *,
    request_id: str,
) -> OutlineApproval:
    revision = get_outline_revision(session, outline_revision_id, context.organization_id)
    draft = get_draft(session, revision.draft_id, context.organization_id, for_update=True)
    if not draft.current_intent_revision_id:
        raise WorkspaceValidationError("an intent revision is required before approval")
    existing = session.scalar(
        select(OutlineApproval).where(
            OutlineApproval.outline_revision_id == outline_revision_id,
            OutlineApproval.organization_id == context.organization_id,
        )
    )
    if existing is not None:
        return existing
    source_summary: dict[str, Any] = {"sourceId": None, "status": "none", "artifacts": 0}
    if draft.source_id:
        source = session.scalar(
            select(Source).where(
                Source.id == draft.source_id,
                Source.organization_id == context.organization_id,
            )
        )
        if source is not None:
            artifact_count = session.scalar(
                select(func.count(SourceArtifact.id)).where(
                    SourceArtifact.source_id == source.id,
                    SourceArtifact.organization_id == context.organization_id,
                )
            )
            source_summary = {
                "sourceId": source.id,
                "status": source.status,
                "sha256": source.source_sha256,
                "parserVersion": source.parser_version,
                "artifacts": int(artifact_count or 0),
            }
    snapshot_input = {
        "draftId": draft.id,
        "intentRevisionId": draft.current_intent_revision_id,
        "outlineRevisionId": revision.id,
        "templateVersionId": draft.template_version_id,
        "mode": draft.mode,
        "sourceSummary": source_summary,
    }
    now = datetime.now(UTC)
    approval = OutlineApproval(
        id=new_ulid(),
        organization_id=context.organization_id,
        draft_id=draft.id,
        outline_revision_id=revision.id,
        intent_revision_id=draft.current_intent_revision_id,
        template_version_id=draft.template_version_id,
        mode=draft.mode,
        source_summary=source_summary,
        snapshot_input_hash=canonical_sha256(snapshot_input),
        approved_by=context.user_id,
        approved_at=now,
    )
    session.add(approval)
    draft.approved_outline_revision_id = revision.id
    draft.status = "approved"
    draft.lock_version += 1
    draft.updated_at = now
    append_audit(
        session,
        context,
        resource_type="outline_revision",
        resource_id=revision.id,
        action="outline.approve",
        request_id=request_id,
        outcome="succeeded",
        details={"snapshotInputHash": approval.snapshot_input_hash},
    )
    session.flush()
    return approval


def serialize_template_version(template: Template, version: TemplateVersion) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "templateId": template.id,
        "templateVersionId": version.id,
        "name": template.name,
        "category": template.category,
        "description": template.description,
        "mode": version.mode,
        "themeSpec": version.theme_spec,
        "pageRoles": version.page_roles,
        "editableElements": version.editable_elements,
        "engineCompatibility": version.engine_compatibility,
        "contentSha256": version.content_sha256,
        "createdAt": _utc(version.created_at),
    }


def list_templates(session: Session, *, category: str | None = None) -> list[dict[str, Any]]:
    seed_builtin_templates(session)
    statement = (
        select(Template, TemplateVersion)
        .join(TemplateVersion, TemplateVersion.template_id == Template.id)
        .where(Template.is_active.is_(True), Template.is_builtin.is_(True))
        .order_by(Template.sort_order, Template.id)
    )
    if category:
        statement = statement.where(Template.category == category)
    return [
        serialize_template_version(template, version)
        for template, version in session.execute(statement)
    ]


def get_template_catalog_version(
    session: Session, template_id: str, template_version_id: str
) -> dict[str, Any]:
    seed_builtin_templates(session)
    row = session.execute(
        select(Template, TemplateVersion)
        .join(TemplateVersion, TemplateVersion.template_id == Template.id)
        .where(
            Template.id == template_id,
            TemplateVersion.id == template_version_id,
            TemplateVersion.template_id == template_id,
            Template.is_active.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise WorkspaceNotFound("template version does not exist")
    return serialize_template_version(row[0], row[1])


def serialize_draft(row: Draft) -> dict[str, Any]:
    return {
        "draftId": row.id,
        "title": row.title,
        "topic": row.topic,
        "sourceId": row.source_id,
        "mode": row.mode,
        "templateVersionId": row.template_version_id,
        "currentIntentRevisionId": row.current_intent_revision_id,
        "currentOutlineRevisionId": row.current_outline_revision_id,
        "approvedOutlineRevisionId": row.approved_outline_revision_id,
        "status": row.status,
        "lockVersion": row.lock_version,
        "createdAt": _utc(row.created_at),
        "updatedAt": _utc(row.updated_at),
    }


def serialize_intent_revision(row: IntentRevision) -> dict[str, Any]:
    return {
        **row.payload,
        "draftId": row.draft_id,
        "basedOnRevisionId": row.based_on_revision_id,
        "actor": {"id": row.actor_id, "kind": row.actor_kind},
        "providerCallId": row.provider_call_id,
        "payloadSha256": row.payload_sha256,
        "createdAt": _utc(row.created_at),
    }


def serialize_outline_revision(session: Session, row: OutlineRevision) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "outlineRevisionId": row.id,
        "draftId": row.draft_id,
        "basedOnRevisionId": row.based_on_revision_id,
        "actor": {"id": row.actor_id, "kind": row.actor_kind},
        "providerCallId": row.provider_call_id,
        "operation": row.operation,
        "storySummary": row.story_summary,
        "targetSlideCount": row.target_slide_count,
        "slides": [
            {
                "outlineSlideId": slide.outline_slide_id,
                "type": slide.slide_type,
                "title": slide.title,
                "keyPoints": slide.key_points,
                "sourceCitations": slide.source_citations,
            }
            for slide in _slides_for(session, row.id)
        ],
        "payloadSha256": row.payload_sha256,
        "createdAt": _utc(row.created_at),
    }


def serialize_approval(row: OutlineApproval) -> dict[str, Any]:
    return {
        "approvalId": row.id,
        "draftId": row.draft_id,
        "intentRevisionId": row.intent_revision_id,
        "outlineRevisionId": row.outline_revision_id,
        "templateVersionId": row.template_version_id,
        "mode": row.mode,
        "sourceSummary": row.source_summary,
        "snapshotInputHash": row.snapshot_input_hash,
        "approvedBy": row.approved_by,
        "approvedAt": _utc(row.approved_at),
        "boundary": "generation_not_started",
    }


def list_history(
    session: Session, organization_id: str, *, cursor: str | None, limit: int
) -> tuple[list[dict[str, Any]], str | None]:
    statement = select(Draft).where(
        Draft.organization_id == organization_id, Draft.deleted_at.is_(None)
    )
    if cursor:
        statement = statement.where(Draft.id < cursor)
    rows = list(session.scalars(statement.order_by(Draft.id.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    visible = rows[:limit]
    items: list[dict[str, Any]] = []
    for row in visible:
        job = session.scalar(
            select(GenerationJob)
            .join(GenerationSnapshot, GenerationSnapshot.id == GenerationJob.snapshot_id)
            .where(
                GenerationSnapshot.draft_id == row.id,
                GenerationJob.organization_id == organization_id,
            )
            .order_by(GenerationJob.created_at.desc())
            .limit(1)
        )
        presentation = session.scalar(
            select(Presentation)
            .where(
                Presentation.draft_id == row.id,
                Presentation.organization_id == organization_id,
                Presentation.deleted_at.is_(None),
            )
            .order_by(Presentation.updated_at.desc())
            .limit(1)
        )
        item = serialize_draft(row)
        item.update(
            {
                "historyState": (
                    "result"
                    if presentation is not None
                    else "monitor"
                    if job is not None
                    else "draft"
                ),
                "jobId": job.id if job else None,
                "jobStatus": job.status if job else None,
                "presentationId": presentation.id if presentation else None,
                "presentationStatus": presentation.status if presentation else None,
                "route": (
                    f"/?draft={row.id}&presentation={presentation.id}"
                    if presentation
                    else f"/?draft={row.id}&job={job.id}"
                    if job
                    else f"/?draft={row.id}"
                ),
            }
        )
        items.append(item)
    return items, visible[-1].id if has_more else None
