"""G04 source upload and durable status HTTP surface."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from instant_ppt_domain.artifacts import ArtifactUnavailable
from instant_ppt_domain.service import IdempotencyConflict
from instant_ppt_domain.sources import (
    SourceNotFound,
    SourceRetryRejected,
    UploadValidationError,
    complete_upload_session,
    create_upload_session,
    get_source,
    get_upload_session,
    list_source_artifacts,
    retry_source_processing,
    serialize_source,
    serialize_upload_session,
)
from instant_ppt_domain.tenancy import (
    find_user_idempotency,
    store_user_idempotency,
)

from instant_ppt_api.auth import AuthDependency
from instant_ppt_api.problems import problem_response
from instant_ppt_api.schemas import CreateUploadSessionRequest, MutationRequest

router = APIRouter(prefix="/v1")


def _upload_response(
    upload_data: dict[str, Any],
    source_id: str,
    *,
    policy_url: str,
    policy_fields: dict[str, str],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "resourceId": upload_data["uploadSessionId"],
        "resourceType": "uploadSession",
        "data": {
            **upload_data,
            "sourceId": source_id,
            "method": "POST",
            "uploadUrl": policy_url,
            "formFields": policy_fields,
        },
        "nextCursor": None,
    }


def _sign_upload(request: Request, upload: Any) -> tuple[str, dict[str, str]]:
    policy = request.app.state.object_store.presign_post(
        upload.object_key,
        content_type=upload.declared_mime_type,
        sha256=upload.expected_sha256,
        size_bytes=upload.expected_size_bytes,
        expires_at=upload.expires_at,
    )
    return policy.url, policy.fields


@router.post("/upload-sessions", status_code=201)
def create_source_upload_session(
    payload: CreateUploadSessionRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = "POST /v1/upload-sessions"
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
            if replay is not None:
                upload = get_upload_session(session, replay.resource_id, auth.organization_id)
                if upload.status != "pending":
                    return problem_response(
                        status=409,
                        code="upload_session_closed",
                        title="上传会话已关闭",
                        detail="已完成或拒绝的上传会话不能重新签发上传凭据",
                        instance=str(request.url.path),
                        request_id=request.state.request_id,
                    )
                if upload.expires_at <= datetime.now(UTC):
                    return problem_response(
                        status=410,
                        code="upload_session_expired",
                        title="上传会话已过期",
                        detail="请使用新的幂等键创建上传会话",
                        instance=str(request.url.path),
                        request_id=request.state.request_id,
                    )
                source_id = upload.source_id
                upload_data = serialize_upload_session(upload)
                replayed = True
            else:
                data = payload.data
                created = create_upload_session(
                    session,
                    auth,
                    filename=data.filename,
                    declared_mime_type=data.declared_mime_type,
                    expected_sha256=data.expected_sha256,
                    size_bytes=data.size_bytes,
                    ttl_seconds=request.app.state.settings.upload_session_ttl_seconds,
                    request_id=request.state.request_id,
                )
                upload = created.upload_session
                source_id = created.source.id
                upload_data = serialize_upload_session(upload)
                stored_body = _upload_response(
                    upload_data,
                    source_id,
                    policy_url="",
                    policy_fields={},
                )
                store_user_idempotency(
                    session,
                    auth,
                    route=route,
                    key=idempotency_key,
                    request_body=body,
                    resource_id=upload.id,
                    response_body=stored_body,
                    response_status=201,
                )
                replayed = False
        policy_url, policy_fields = _sign_upload(request, upload)
        return JSONResponse(
            _upload_response(
                upload_data,
                source_id,
                policy_url=policy_url,
                policy_fields=policy_fields,
            ),
            status_code=201,
            headers={
                "Cache-Control": "no-store",
                "Idempotency-Replayed": str(replayed).lower(),
                "Location": f"/v1/sources/{source_id}",
            },
        )
    except UploadValidationError as error:
        return problem_response(
            status=422,
            code="invalid_source_upload",
            title="上传参数无效",
            detail=str(error),
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
    except ArtifactUnavailable:
        return problem_response(
            status=503,
            code="object_store_unavailable",
            title="上传服务暂不可用",
            detail="暂时无法签发私有上传凭据，请稍后重试",
            instance=str(request.url.path),
            retryable=True,
            request_id=request.state.request_id,
        )


@router.post("/upload-sessions/{upload_session_id}:complete", status_code=202)
def complete_source_upload_session(
    upload_session_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/upload-sessions/{upload_session_id}:complete"
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
            if replay is not None:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={
                        "Cache-Control": "no-store",
                        "Idempotency-Replayed": "true",
                        "Location": f"/v1/sources/{replay.resource_id}",
                    },
                )
            upload = get_upload_session(session, upload_session_id, auth.organization_id)
            digest = request.app.state.object_store.digest(
                upload.object_key, max_bytes=upload.max_bytes
            )
            completed = complete_upload_session(
                session,
                auth,
                upload_session_id,
                digest=digest,
                request_id=request.state.request_id,
            )
            source_data = serialize_source(completed.source)
            response_body = {
                "schemaVersion": 1,
                "resourceId": completed.source.id,
                "resourceType": "source",
                "data": source_data,
                "nextCursor": None,
            }
            status_code = (
                202
                if completed.accepted
                else (410 if completed.rejection_code == "UPLOAD_SESSION_EXPIRED" else 422)
            )
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=completed.source.id,
                response_body=response_body,
                response_status=status_code,
            )
        return JSONResponse(
            response_body,
            status_code=status_code,
            headers={
                "Cache-Control": "no-store",
                "Idempotency-Replayed": "false",
                "Location": f"/v1/sources/{completed.source.id}",
            },
        )
    except SourceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="上传会话不存在或无权访问",
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
    except ArtifactUnavailable:
        return problem_response(
            status=503,
            code="upload_object_unavailable",
            title="上传对象暂不可用",
            detail="无法复核隔离区对象，请稍后重试",
            instance=str(request.url.path),
            retryable=True,
            request_id=request.state.request_id,
        )


@router.get("/sources/{source_id}")
def get_source_status(
    source_id: str,
    request: Request,
    auth: AuthDependency,
) -> JSONResponse:
    try:
        with request.app.state.session_factory() as session:
            source = get_source(session, source_id, auth.organization_id)
            data = serialize_source(source)
            data["artifacts"] = list_source_artifacts(session, source_id, auth.organization_id)
        return JSONResponse(
            {
                "schemaVersion": 1,
                "resourceId": source_id,
                "resourceType": "source",
                "data": data,
                "nextCursor": None,
            },
            headers={"Cache-Control": "no-store"},
        )
    except SourceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="来源不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )


@router.post("/sources/{source_id}:retry-parse", status_code=202)
def retry_source_parse(
    source_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/sources/{source_id}:retry-parse"
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
            if replay is not None:
                return JSONResponse(
                    replay.response_body,
                    status_code=replay.response_status,
                    headers={
                        "Idempotency-Replayed": "true",
                        "Location": f"/v1/sources/{source_id}",
                    },
                )
            source = retry_source_processing(
                session,
                auth,
                source_id,
                request_id=request.state.request_id,
            )
            response_body = {
                "schemaVersion": 1,
                "resourceId": source.id,
                "resourceType": "source",
                "data": serialize_source(source),
                "nextCursor": None,
            }
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=source.id,
                response_body=response_body,
                response_status=202,
            )
        return JSONResponse(
            response_body,
            status_code=202,
            headers={
                "Idempotency-Replayed": "false",
                "Location": f"/v1/sources/{source_id}",
            },
        )
    except SourceNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="来源不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except SourceRetryRejected as error:
        return problem_response(
            status=409,
            code="source_not_retryable",
            title="当前来源不能重试",
            detail=str(error),
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
