"""G07 revision-safe editor, regeneration, exports, and data portability API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from instant_ppt_domain.artifacts import ArtifactUnavailable
from instant_ppt_domain.models import SlideRegenerationJob
from instant_ppt_domain.presentation import (
    PresentationConflict,
    PresentationNotFound,
    PresentationValidationError,
    create_export_job,
    create_regeneration_job,
    create_revision,
    export_draft_data,
    get_data_export,
    get_export_job,
    get_presentation,
    get_revision,
    list_revisions,
    serialize_data_export,
    serialize_export_job,
    serialize_presentation,
    serialize_regeneration_job,
    serialize_revision,
)
from instant_ppt_domain.service import IdempotencyConflict
from instant_ppt_domain.tenancy import find_user_idempotency, store_user_idempotency
from sqlalchemy import select

from instant_ppt_api.auth import AuthDependency
from instant_ppt_api.problems import problem_response
from instant_ppt_api.schemas import (
    MutationRequest,
    PresentationExportRequest,
    PresentationRevisionRequest,
    SlideRegenerationRequest,
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


def _problem(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, PresentationNotFound):
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="资源不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    if isinstance(error, PresentationConflict):
        return problem_response(
            status=412,
            code="revision_conflict",
            title="演示文稿已更新",
            detail="当前版本已变化，请保留输入并刷新后重试",
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
    if isinstance(error, ArtifactUnavailable):
        return problem_response(
            status=503,
            code="artifact_store_unavailable",
            title="制品存储暂不可用",
            detail="请稍后重试，当前版本未发生变化",
            instance=str(request.url.path),
            request_id=request.state.request_id,
            retryable=True,
        )
    return problem_response(
        status=422,
        code="validation_error",
        title="请求参数无效",
        detail=str(error),
        instance=str(request.url.path),
        request_id=request.state.request_id,
    )


@router.get("/presentations/{presentation_id}")
def get_presentation_resource(
    presentation_id: str, request: Request, auth: AuthDependency
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            row = get_presentation(session, presentation_id, auth.organization_id)
            body = _resource(row.id, "presentation", serialize_presentation(session, row))
        return JSONResponse(body, headers={"Cache-Control": "no-store"})
    except PresentationNotFound as error:
        return _problem(request, error)


@router.get("/presentations/{presentation_id}/revisions")
def list_presentation_revisions(
    presentation_id: str,
    request: Request,
    auth: AuthDependency,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            rows, next_cursor = list_revisions(
                session,
                presentation_id,
                auth.organization_id,
                cursor=cursor,
                limit=limit,
            )
            items = [serialize_revision(session, row) for row in rows]
        return JSONResponse(
            _resource(
                presentation_id, "presentationRevisionList", {"items": items}, cursor=next_cursor
            )
        )
    except PresentationNotFound as error:
        return _problem(request, error)


@router.get("/presentation-revisions/{revision_id}")
def get_presentation_revision_resource(
    revision_id: str, request: Request, auth: AuthDependency
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            row = get_revision(session, revision_id, auth.organization_id)
            body = _resource(row.id, "presentationRevision", serialize_revision(session, row))
        return JSONResponse(body)
    except PresentationNotFound as error:
        return _problem(request, error)


@router.post("/presentations/{presentation_id}/revisions", status_code=201)
def create_presentation_revision_resource(
    presentation_id: str,
    payload: PresentationRevisionRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/presentations/{presentation_id}/revisions"
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
            row = create_revision(
                session,
                auth,
                presentation_id,
                base_revision_id=payload.base_revision_id,
                operations=[
                    item.model_dump(by_alias=True, exclude_none=True, mode="json")
                    for item in payload.data.operations
                ],
                object_store=request.app.state.object_store,
                request_id=request.state.request_id,
            )
            response_body = _resource(
                row.id, "presentationRevision", serialize_revision(session, row)
            )
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
            headers={"Idempotency-Replayed": "false"},
        )
    except (
        PresentationNotFound,
        PresentationConflict,
        PresentationValidationError,
        IdempotencyConflict,
        ArtifactUnavailable,
    ) as error:
        return _problem(request, error)


@router.post("/presentations/{presentation_id}/slides/{slide_id}:regenerate", status_code=202)
def regenerate_presentation_slide(
    presentation_id: str,
    slide_id: str,
    payload: SlideRegenerationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/presentations/{presentation_id}/slides/{slide_id}:regenerate"
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
                        "Location": f"/v1/operations/{replay.resource_id}",
                    },
                )
            row = create_regeneration_job(
                session,
                auth,
                presentation_id,
                slide_id,
                base_revision_id=payload.base_revision_id,
                instruction=payload.data.instruction,
                request_id=request.state.request_id,
            )
            response_body = _resource(
                row.id, "slideRegenerationJob", serialize_regeneration_job(row)
            )
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=row.id,
                response_body=response_body,
                response_status=202,
            )
        return JSONResponse(
            response_body,
            status_code=202,
            headers={
                "Idempotency-Replayed": "false",
                "Location": f"/v1/operations/{row.id}",
            },
        )
    except (
        PresentationNotFound,
        PresentationConflict,
        PresentationValidationError,
        IdempotencyConflict,
    ) as error:
        return _problem(request, error)


@router.get("/operations/{operation_id}")
def get_operation(operation_id: str, request: Request, auth: AuthDependency) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            regeneration = session.scalar(
                select(SlideRegenerationJob).where(
                    SlideRegenerationJob.id == operation_id,
                    SlideRegenerationJob.organization_id == auth.organization_id,
                )
            )
            if regeneration is not None:
                get_presentation(session, regeneration.presentation_id, auth.organization_id)
                return JSONResponse(
                    _resource(
                        regeneration.id,
                        "slideRegenerationJob",
                        serialize_regeneration_job(regeneration),
                    )
                )
            export = get_export_job(session, operation_id, auth.organization_id)
            return JSONResponse(
                _resource(export.id, "presentationExport", serialize_export_job(export))
            )
    except PresentationNotFound as error:
        return _problem(request, error)


@router.post("/presentations/{presentation_id}/exports", status_code=202)
def create_presentation_export(
    presentation_id: str,
    payload: PresentationExportRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/presentations/{presentation_id}/exports"
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
                        "Location": f"/v1/exports/{replay.resource_id}",
                    },
                )
            presentation = get_presentation(session, presentation_id, auth.organization_id)
            revision_id = (
                payload.data.presentation_revision_id
                or payload.base_revision_id
                or presentation.current_revision_id
            )
            if revision_id is None:
                raise PresentationValidationError("presentationRevisionId is required")
            row = create_export_job(
                session,
                auth,
                presentation_id,
                revision_id=revision_id,
                options=payload.data.model_dump(by_alias=True, exclude_none=True, mode="json"),
                request_id=request.state.request_id,
            )
            response_body = _resource(row.id, "presentationExport", serialize_export_job(row))
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=row.id,
                response_body=response_body,
                response_status=202,
            )
        return JSONResponse(
            response_body,
            status_code=202,
            headers={
                "Idempotency-Replayed": "false",
                "Location": f"/v1/exports/{row.id}",
            },
        )
    except (
        PresentationNotFound,
        PresentationValidationError,
        IdempotencyConflict,
    ) as error:
        return _problem(request, error)


@router.get("/exports/{export_id}")
def get_presentation_export(export_id: str, request: Request, auth: AuthDependency) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            row = get_export_job(session, export_id, auth.organization_id)
            body = _resource(row.id, "presentationExport", serialize_export_job(row))
        return JSONResponse(body)
    except PresentationNotFound as error:
        return _problem(request, error)


@router.post("/drafts/{draft_id}:export-data", status_code=202)
def create_draft_data_export(
    draft_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/drafts/{draft_id}:export-data"
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
            row = export_draft_data(
                session,
                auth,
                draft_id,
                object_store=request.app.state.object_store,
                request_id=request.state.request_id,
            )
            response_body = _resource(row.id, "dataExport", serialize_data_export(row))
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=row.id,
                response_body=response_body,
                response_status=202,
            )
        return JSONResponse(
            response_body,
            status_code=202,
            headers={"Idempotency-Replayed": "false"},
        )
    except (
        PresentationNotFound,
        IdempotencyConflict,
        ArtifactUnavailable,
    ) as error:
        return _problem(request, error)


@router.get("/data-exports/{export_id}")
def get_draft_data_export(export_id: str, request: Request, auth: AuthDependency) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            row = get_data_export(session, export_id, auth.organization_id)
            body = _resource(row.id, "dataExport", serialize_data_export(row))
        return JSONResponse(body)
    except PresentationNotFound as error:
        return _problem(request, error)
