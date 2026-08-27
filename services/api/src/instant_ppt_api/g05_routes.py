"""G05 draft workspace, revisions, templates, planning, approval, and history API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from instant_ppt_domain.models import OutlineApproval, ProviderCall
from instant_ppt_domain.planning_jobs import (
    enqueue_intent_job,
    enqueue_outline_job,
    get_planning_job,
    latest_planning_job,
    planning_job_result,
    serialize_planning_job,
)
from instant_ppt_domain.service import IdempotencyConflict
from instant_ppt_domain.tenancy import find_user_idempotency, store_user_idempotency
from instant_ppt_domain.workspace import (
    WorkspaceConflict,
    WorkspaceNotFound,
    WorkspaceValidationError,
    approve_outline,
    create_draft,
    create_intent_revision,
    create_outline_revision,
    delete_draft,
    get_draft,
    get_intent_revision,
    get_outline_revision,
    get_template_catalog_version,
    list_history,
    list_intent_revisions,
    list_outline_revisions,
    list_templates,
    serialize_approval,
    serialize_draft,
    serialize_intent_revision,
    serialize_outline_revision,
    update_draft,
)
from sqlalchemy import select

from instant_ppt_api.auth import AuthDependency
from instant_ppt_api.planning import PlanningSchemaError, PlanningUnavailableError
from instant_ppt_api.problems import problem_response
from instant_ppt_api.schemas import (
    CreateDraftRequest,
    GenerateOutlineRequest,
    IntentRevisionRequest,
    MutationRequest,
    OutlineRevisionRequest,
    UpdateDraftRequest,
)

router = APIRouter(prefix="/v1")


def _resource(resource_id: str, resource_type: str, data: Any, *, cursor: str | None = None):
    return {
        "schemaVersion": 1,
        "resourceId": resource_id,
        "resourceType": resource_type,
        "data": data,
        "nextCursor": cursor,
    }


def _etag(lock_version: int) -> str:
    return f'"{lock_version}"'


def _parse_if_match(value: str | None) -> int:
    if not value:
        raise WorkspaceValidationError("If-Match is required")
    candidate = value.strip()
    if candidate.startswith("W/"):
        candidate = candidate[2:]
    candidate = candidate.strip('"')
    if not candidate.isdigit() or int(candidate) < 1:
        raise WorkspaceValidationError("If-Match must contain the draft lock version")
    return int(candidate)


def _problem(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, WorkspaceNotFound):
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="资源不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    if isinstance(error, WorkspaceConflict):
        return problem_response(
            status=412,
            code="revision_conflict",
            title="内容已在其他位置更新",
            detail="请保留本地输入，刷新最新版本后重试",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    if isinstance(error, IdempotencyConflict):
        return problem_response(
            status=409,
            code="idempotency_key_reused",
            title="幂等键已被不同请求使用",
            detail=str(error),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    if isinstance(error, PlanningSchemaError):
        return problem_response(
            status=502,
            code="provider_schema_failed",
            title="AI 返回结构无法使用",
            detail="自动修复已达到上限，请手工编辑或稍后重试",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    if isinstance(error, PlanningUnavailableError):
        if error.upstream_code:
            detail = f"上游 AI 服务暂时不可用（{error.upstream_code}）"
        elif error.upstream_status is not None:
            detail = f"上游 AI 服务暂时不可用（HTTP {error.upstream_status}）"
        elif error.failure_kind:
            detail = f"上游 AI 连接失败（{error.failure_kind}）"
        else:
            detail = "请求未完成，请稍后重试"
        return problem_response(
            status=503,
            code="provider_unavailable",
            title="AI 服务暂时不可用",
            detail=detail,
            instance=str(request.url.path),
            retryable=True,
            request_id=request.state.request_id,
        )
    return problem_response(
        status=422,
        code="validation_error",
        title="请求参数无效",
        detail=str(error),
        instance=str(request.url.path),
        request_id=request.state.request_id,
    )


def _snapshot(session: Any, draft: Any) -> dict[str, Any]:
    data = serialize_draft(draft)
    data["currentIntent"] = (
        serialize_intent_revision(
            get_intent_revision(session, draft.current_intent_revision_id, draft.organization_id)
        )
        if draft.current_intent_revision_id
        else None
    )
    data["currentOutline"] = (
        serialize_outline_revision(
            session,
            get_outline_revision(session, draft.current_outline_revision_id, draft.organization_id),
        )
        if draft.current_outline_revision_id
        else None
    )
    approval = None
    if draft.approved_outline_revision_id:
        approval = session.scalar(
            select(OutlineApproval).where(
                OutlineApproval.outline_revision_id == draft.approved_outline_revision_id,
                OutlineApproval.organization_id == draft.organization_id,
            )
        )
    data["generationSummary"] = serialize_approval(approval) if approval else None
    planning_provider = session.scalar(
        select(ProviderCall)
        .where(
            ProviderCall.draft_id == draft.id,
            ProviderCall.organization_id == draft.organization_id,
            ProviderCall.status == "succeeded",
        )
        .order_by(ProviderCall.started_at.desc(), ProviderCall.id.desc())
        .limit(1)
    )
    data["planningProvider"] = (
        {
            "provider": planning_provider.provider,
            "model": planning_provider.model,
            "purpose": planning_provider.purpose,
        }
        if planning_provider
        else None
    )
    planning_job = latest_planning_job(session, draft.id, draft.organization_id)
    data["planningJob"] = serialize_planning_job(planning_job) if planning_job else None
    return data


@router.post("/drafts", status_code=201)
def create_workspace_draft(
    payload: CreateDraftRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = "POST /v1/drafts"
    body = payload.model_dump(by_alias=True, mode="json")
    try:
        with request.app.state.session_factory.begin() as session:
            replay = find_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
            )
            if replay:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={
                        "Idempotency-Replayed": "true",
                        "Location": f"/v1/drafts/{replay.resource_id}",
                        "ETag": _etag(replay.response_body["data"]["lockVersion"]),
                    },
                )
            row = create_draft(
                session,
                auth,
                topic=payload.data.topic,
                source_id=payload.data.source_id,
                template_version_id=payload.data.template_version_id,
                request_id=request.state.request_id,
            )
            response_body = _resource(row.id, "draft", serialize_draft(row))
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=row.id,
                response_body=response_body,
                response_status=201,
            )
        return JSONResponse(
            response_body,
            status_code=201,
            headers={
                "Idempotency-Replayed": "false",
                "Location": f"/v1/drafts/{row.id}",
                "ETag": _etag(row.lock_version),
            },
        )
    except (WorkspaceValidationError, IdempotencyConflict) as error:
        return _problem(request, error)


@router.get("/drafts/{draft_id}")
def get_workspace_draft(draft_id: str, request: Request, auth: AuthDependency) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            row = get_draft(session, draft_id, auth.organization_id)
            body = _resource(row.id, "draft", _snapshot(session, row))
            lock_version = row.lock_version
        return JSONResponse(
            body,
            headers={"ETag": _etag(lock_version), "Cache-Control": "no-store"},
        )
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.patch("/drafts/{draft_id}")
def patch_workspace_draft(
    draft_id: str,
    payload: UpdateDraftRequest,
    request: Request,
    auth: AuthDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    try:
        version = _parse_if_match(if_match)
        with request.app.state.session_factory.begin() as session:
            row = update_draft(
                session,
                auth,
                draft_id,
                lock_version=version,
                topic=payload.data.topic,
                title=payload.data.title,
                template_version_id=payload.data.template_version_id,
                request_id=request.state.request_id,
            )
            body = _resource(row.id, "draft", serialize_draft(row))
        return JSONResponse(body, headers={"ETag": _etag(row.lock_version)})
    except (WorkspaceNotFound, WorkspaceConflict, WorkspaceValidationError) as error:
        return _problem(request, error)


@router.delete("/drafts/{draft_id}", status_code=204, response_class=Response)
def remove_workspace_draft(draft_id: str, request: Request, auth: AuthDependency) -> Response:
    try:
        with request.app.state.session_factory.begin() as session:
            delete_draft(session, auth, draft_id, request_id=request.state.request_id)
        return Response(status_code=204)
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.post("/drafts/{draft_id}/intent:infer", status_code=202)
def infer_workspace_intent(
    draft_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/drafts/{draft_id}/intent:infer"
    body = payload.model_dump(by_alias=True, mode="json")
    try:
        with request.app.state.session_factory.begin() as session:
            replay = find_user_idempotency(
                session, auth, route=route, key=idempotency_key, request_body=body
            )
            if replay:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={
                        "Idempotency-Replayed": "true",
                        "Location": f"/v1/planning-jobs/{replay.resource_id}",
                    },
                )
            job = enqueue_intent_job(
                session,
                auth,
                draft_id,
                language=str(payload.data.get("language") or "zh-CN"),
                base_revision_id=payload.base_revision_id,
                request_id=request.state.request_id,
            )
            response_body = _resource(
                job.id, "planningJob", serialize_planning_job(job)
            )
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=job.id,
                response_body=response_body,
                response_status=202,
            )
        return JSONResponse(
            response_body,
            status_code=202,
            headers={
                "Idempotency-Replayed": "false",
                "Location": f"/v1/planning-jobs/{job.id}",
            },
        )
    except (
        WorkspaceNotFound,
        WorkspaceConflict,
        WorkspaceValidationError,
        IdempotencyConflict,
    ) as error:
        return _problem(request, error)


@router.get("/planning-jobs/{job_id}")
def get_workspace_planning_job(
    job_id: str, request: Request, auth: AuthDependency
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            job = get_planning_job(session, job_id, auth.organization_id)
            data = serialize_planning_job(job)
            data["result"] = planning_job_result(session, job)
            body = _resource(job.id, "planningJob", data)
        return JSONResponse(body)
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.post("/drafts/{draft_id}/intent-revisions", status_code=201)
def create_workspace_intent_revision(
    draft_id: str,
    payload: IntentRevisionRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/drafts/{draft_id}/intent-revisions"
    body = payload.model_dump(by_alias=True, mode="json")
    try:
        with request.app.state.session_factory.begin() as session:
            replay = find_user_idempotency(
                session, auth, route=route, key=idempotency_key, request_body=body
            )
            if replay:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={"Idempotency-Replayed": "true"},
                )
            revision = create_intent_revision(
                session,
                auth,
                draft_id,
                data=payload.data.model_dump(by_alias=True, mode="json"),
                based_on_revision_id=payload.base_revision_id,
                actor_kind="user",
                provider_call_id=None,
                request_id=request.state.request_id,
            )
            response_body = _resource(
                revision.id, "intentRevision", serialize_intent_revision(revision)
            )
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=revision.id,
                response_body=response_body,
                response_status=201,
            )
        return JSONResponse(
            response_body,
            status_code=201,
            headers={"Idempotency-Replayed": "false"},
        )
    except (
        WorkspaceNotFound,
        WorkspaceConflict,
        WorkspaceValidationError,
        IdempotencyConflict,
    ) as error:
        return _problem(request, error)


@router.get("/drafts/{draft_id}/intent-revisions")
def list_workspace_intent_revisions(
    draft_id: str, request: Request, auth: AuthDependency
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            rows = list_intent_revisions(session, draft_id, auth.organization_id)
            data = [serialize_intent_revision(row) for row in rows]
        return JSONResponse(_resource(draft_id, "intentRevisionList", {"items": data}))
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.get("/intent-revisions/{revision_id}")
def get_workspace_intent_revision(
    revision_id: str, request: Request, auth: AuthDependency
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            row = get_intent_revision(session, revision_id, auth.organization_id)
            body = _resource(row.id, "intentRevision", serialize_intent_revision(row))
        return JSONResponse(body)
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.post("/drafts/{draft_id}/outline:generate", status_code=202)
def generate_workspace_outline(
    draft_id: str,
    payload: GenerateOutlineRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/drafts/{draft_id}/outline:generate"
    body = payload.model_dump(by_alias=True, mode="json")
    try:
        with request.app.state.session_factory.begin() as session:
            replay = find_user_idempotency(
                session, auth, route=route, key=idempotency_key, request_body=body
            )
            if replay:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={
                        "Idempotency-Replayed": "true",
                        "Location": f"/v1/planning-jobs/{replay.resource_id}",
                    },
                )
            job = enqueue_outline_job(
                session,
                auth,
                draft_id,
                action=payload.data.action,
                instruction=payload.data.instruction,
                target_slide_id=payload.data.outline_slide_id,
                base_revision_id=payload.base_revision_id,
                request_id=request.state.request_id,
            )
            response_body = _resource(
                job.id,
                "planningJob",
                serialize_planning_job(job),
            )
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=job.id,
                response_body=response_body,
                response_status=202,
            )
        return JSONResponse(
            response_body,
            status_code=202,
            headers={
                "Idempotency-Replayed": "false",
                "Location": f"/v1/planning-jobs/{job.id}",
            },
        )
    except (
        WorkspaceNotFound,
        WorkspaceConflict,
        WorkspaceValidationError,
        IdempotencyConflict,
    ) as error:
        return _problem(request, error)


@router.post("/drafts/{draft_id}/outline-revisions", status_code=201)
def create_workspace_outline_revision(
    draft_id: str,
    payload: OutlineRevisionRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/drafts/{draft_id}/outline-revisions"
    body = payload.model_dump(by_alias=True, mode="json")
    try:
        with request.app.state.session_factory.begin() as session:
            replay = find_user_idempotency(
                session, auth, route=route, key=idempotency_key, request_body=body
            )
            if replay:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={"Idempotency-Replayed": "true"},
                )
            revision = create_outline_revision(
                session,
                auth,
                draft_id,
                story_summary=payload.data.story_summary,
                target_slide_count=payload.data.target_slide_count,
                slides=[
                    slide.model_dump(by_alias=True, mode="json") for slide in payload.data.slides
                ],
                based_on_revision_id=payload.base_revision_id,
                actor_kind="user",
                operation=payload.data.operation,
                provider_call_id=None,
                request_id=request.state.request_id,
            )
            response_body = _resource(
                revision.id,
                "outlineRevision",
                serialize_outline_revision(session, revision),
            )
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=revision.id,
                response_body=response_body,
                response_status=201,
            )
        return JSONResponse(
            response_body,
            status_code=201,
            headers={"Idempotency-Replayed": "false"},
        )
    except (
        WorkspaceNotFound,
        WorkspaceConflict,
        WorkspaceValidationError,
        IdempotencyConflict,
    ) as error:
        return _problem(request, error)


@router.get("/drafts/{draft_id}/outline-revisions")
def list_workspace_outline_revisions(
    draft_id: str, request: Request, auth: AuthDependency
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            rows = list_outline_revisions(session, draft_id, auth.organization_id)
            data = [serialize_outline_revision(session, row) for row in rows]
        return JSONResponse(_resource(draft_id, "outlineRevisionList", {"items": data}))
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.get("/outline-revisions/{revision_id}")
def get_workspace_outline_revision(
    revision_id: str, request: Request, auth: AuthDependency
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            row = get_outline_revision(session, revision_id, auth.organization_id)
            body = _resource(row.id, "outlineRevision", serialize_outline_revision(session, row))
        return JSONResponse(body)
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.post("/outline-revisions/{revision_id}:approve")
def approve_workspace_outline(
    revision_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/outline-revisions/{revision_id}:approve"
    body = payload.model_dump(by_alias=True, mode="json")
    try:
        with request.app.state.session_factory.begin() as session:
            replay = find_user_idempotency(
                session, auth, route=route, key=idempotency_key, request_body=body
            )
            if replay:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={"Idempotency-Replayed": "true"},
                )
            approval = approve_outline(
                session, auth, revision_id, request_id=request.state.request_id
            )
            response_body = _resource(approval.id, "outlineApproval", serialize_approval(approval))
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=approval.id,
                response_body=response_body,
            )
        return JSONResponse(response_body, headers={"Idempotency-Replayed": "false"})
    except (
        WorkspaceNotFound,
        WorkspaceValidationError,
        IdempotencyConflict,
    ) as error:
        return _problem(request, error)


@router.get("/templates")
def list_builtin_templates(
    request: Request,
    auth: AuthDependency,
    category: Annotated[str | None, Query(max_length=80)] = None,
) -> JSONResponse:
    del auth
    with request.app.state.session_factory.begin() as session:
        items = list_templates(session, category=category)
    return JSONResponse(_resource("builtin", "templateCatalog", {"items": items}))


@router.get("/templates/{template_id}/versions/{template_version_id}")
def get_builtin_template_version(
    template_id: str,
    template_version_id: str,
    request: Request,
    auth: AuthDependency,
) -> JSONResponse:
    del auth
    try:
        with request.app.state.session_factory.begin() as session:
            data = get_template_catalog_version(session, template_id, template_version_id)
        return JSONResponse(_resource(template_version_id, "templateVersion", data))
    except WorkspaceNotFound as error:
        return _problem(request, error)


@router.get("/history")
def get_workspace_history(
    request: Request,
    auth: AuthDependency,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> JSONResponse:
    with request.app.state.session_factory() as session:
        items, next_cursor = list_history(session, auth.organization_id, cursor=cursor, limit=limit)
    return JSONResponse(
        _resource(auth.organization_id, "history", {"items": items}, cursor=next_cursor)
    )
