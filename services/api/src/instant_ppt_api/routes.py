"""Minimal G02 HTTP surface backed by durable orchestration state."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.generation import (
    CreateApprovedJobCommand,
    GenerationApprovalRequired,
    GenerationQuotaExceeded,
    GenerationTemplateUnavailable,
    create_approved_generation_job,
    request_generation_cancel_idempotent,
    retry_generation_slide_idempotent,
)
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import Draft
from instant_ppt_domain.service import (
    CreateJobCommand,
    IdempotencyConflict,
    InvalidTransition,
    ResourceNotFound,
    create_generation_job,
    get_job,
    serialize_job_snapshot,
)
from instant_ppt_domain.tenancy import append_audit
from instant_ppt_domain.workspace import WorkspaceNotFound
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_api.auth import AuthDependency
from instant_ppt_api.events import stream_events
from instant_ppt_api.problems import problem_response
from instant_ppt_api.schemas import CreateGenerationJobRequest, MutationRequest

router = APIRouter(prefix="/v1")


def _factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def _settings(request: Request) -> DomainSettings:
    return request.app.state.settings


@router.post("/drafts/{draft_id}/generation-jobs", status_code=202)
def create_job(
    draft_id: str,
    payload: CreateGenerationJobRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> JSONResponse:
    data = payload.data
    body = payload.model_dump(by_alias=True, mode="json")
    try:
        with _factory(request).begin() as session:
            try:
                result = create_approved_generation_job(
                    session,
                    CreateApprovedJobCommand(
                        context=auth,
                        draft_id=draft_id,
                        idempotency_key=idempotency_key,
                        request_body=body,
                        request_id=request.state.request_id,
                        failure_modes=(
                            dict(data.failure_modes)
                            if _settings(request).app_environment == "test"
                            else {}
                        ),
                        step_delay_ms=(
                            data.step_delay_ms
                            if _settings(request).app_environment == "test"
                            else 0
                        ),
                        crash_once_at_position=(
                            data.crash_once_at_position
                            if _settings(request).app_environment == "test"
                            else None
                        ),
                    ),
                )
            except WorkspaceNotFound:
                existing_any_tenant = session.get(Draft, draft_id)
                if _settings(request).app_environment != "test" or existing_any_tenant is not None:
                    raise
                result = create_generation_job(
                    session,
                    CreateJobCommand(
                        organization_id=auth.organization_id,
                        actor_id=auth.user_id,
                        draft_id=draft_id,
                        idempotency_key=idempotency_key,
                        request_body=body,
                        intent_revision_id=data.intent_revision_id or new_ulid(),
                        outline_revision_id=data.outline_revision_id or new_ulid(),
                        template_version_id=data.template_version_id or new_ulid(),
                        slide_count=data.slide_count,
                        source_hashes=tuple(data.source_hashes),
                        failure_modes=dict(data.failure_modes),
                        step_delay_ms=data.step_delay_ms,
                        crash_once_at_position=data.crash_once_at_position,
                    ),
                )
                append_audit(
                    session,
                    auth,
                    resource_type="generation_job",
                    resource_id=result.job_id,
                    action="generation_job.created",
                    request_id=request.state.request_id,
                    outcome="replayed" if result.replayed else "succeeded",
                )
        headers = {**result.headers, "Idempotency-Replayed": str(result.replayed).lower()}
        return JSONResponse(result.body, status_code=result.status_code, headers=headers)
    except IdempotencyConflict as error:
        return problem_response(
            status=409,
            code="idempotency_key_reused",
            title="幂等键已被不同请求使用",
            detail=str(error),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except WorkspaceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="草稿不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except (GenerationApprovalRequired, GenerationTemplateUnavailable) as error:
        return problem_response(
            status=422,
            code="generation_input_not_ready",
            title="生成输入尚未就绪",
            detail=str(error),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except GenerationQuotaExceeded as error:
        return problem_response(
            status=429,
            code="quota_exceeded",
            title="生成额度不足",
            detail=str(error),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )


@router.get("/jobs/{job_id}")
def get_generation_job(
    job_id: str,
    request: Request,
    auth: AuthDependency,
) -> JSONResponse:
    try:
        with _factory(request)() as session:
            job = get_job(session, job_id, auth.organization_id)
            snapshot = serialize_job_snapshot(session, job)
        return JSONResponse(
            {
                "schemaVersion": 1,
                "resourceId": job_id,
                "resourceType": "generationJob",
                "data": snapshot,
                "nextCursor": None,
            }
        )
    except ResourceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="任务不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )


@router.post("/jobs/{job_id}:cancel", status_code=202)
def cancel_generation_job(
    job_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> JSONResponse:
    try:
        with _factory(request).begin() as session:
            result = request_generation_cancel_idempotent(
                session,
                context=auth,
                job_id=job_id,
                idempotency_key=idempotency_key,
                request_body=payload.model_dump(by_alias=True, mode="json"),
                request_id=request.state.request_id,
            )
        return JSONResponse(
            result.body,
            status_code=result.status_code,
            headers={
                **result.headers,
                "Idempotency-Replayed": str(result.replayed).lower(),
            },
        )
    except ResourceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="任务不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except IdempotencyConflict as error:
        return problem_response(
            status=409,
            code="idempotency_key_reused",
            title="幂等键已被不同请求使用",
            detail=str(error),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )


@router.post("/jobs/{job_id}/slides/{slide_id}:retry", status_code=202)
def retry_generation_slide(
    job_id: str,
    slide_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> JSONResponse:
    try:
        with _factory(request).begin() as session:
            result = retry_generation_slide_idempotent(
                session,
                context=auth,
                job_id=job_id,
                slide_id=slide_id,
                idempotency_key=idempotency_key,
                request_body=payload.model_dump(by_alias=True, mode="json"),
                request_id=request.state.request_id,
            )
        return JSONResponse(
            result.body,
            status_code=result.status_code,
            headers={
                **result.headers,
                "Idempotency-Replayed": str(result.replayed).lower(),
            },
        )
    except ResourceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="任务或页面不存在",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except IdempotencyConflict as error:
        return problem_response(
            status=409,
            code="idempotency_key_reused",
            title="幂等键已被不同请求使用",
            detail=str(error),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except InvalidTransition as error:
        return problem_response(
            status=409,
            code="invalid_state_transition",
            title="当前状态不能重试",
            detail=str(error),
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )


@router.get("/jobs/{job_id}/events", response_model=None)
async def generation_job_events(
    job_id: str,
    request: Request,
    auth: AuthDependency,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse | JSONResponse:
    try:
        with _factory(request)() as session:
            get_job(session, job_id, auth.organization_id)
    except ResourceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="任务不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    settings = _settings(request)
    return StreamingResponse(
        stream_events(
            request,
            _factory(request),
            redis_url=settings.redis_events_url,
            job_id=job_id,
            organization_id=auth.organization_id,
            last_event_id=last_event_id,
            heartbeat_seconds=settings.sse_heartbeat_seconds,
            metrics=request.app.state.observability.metrics,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
