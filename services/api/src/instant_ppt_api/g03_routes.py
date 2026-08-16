"""G03 identity, entitlement, usage, and private artifact HTTP surface."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from instant_ppt_domain.artifacts import (
    ArtifactNotFound,
    ArtifactUnavailable,
    DownloadAuthorizationExpired,
    authorize_download,
    replay_download_authorization,
)
from instant_ppt_domain.service import IdempotencyConflict
from instant_ppt_domain.tenancy import (
    entitlement_snapshot,
    find_user_idempotency,
    store_user_idempotency,
    usage_snapshot,
)

from instant_ppt_api.auth import AuthDependency
from instant_ppt_api.problems import problem_response
from instant_ppt_api.schemas import MutationRequest

router = APIRouter(prefix="/v1")


@router.get("/me/entitlements")
def get_my_entitlements(request: Request, auth: AuthDependency) -> JSONResponse:
    with request.app.state.session_factory() as session:
        data = entitlement_snapshot(session, auth.organization_id)
    return JSONResponse(
        {
            "schemaVersion": 1,
            "resourceId": auth.organization_id,
            "resourceType": "entitlements",
            "data": data,
            "nextCursor": None,
        }
    )


@router.get("/me/usage")
def get_my_usage(request: Request, auth: AuthDependency) -> JSONResponse:
    with request.app.state.session_factory() as session:
        data = usage_snapshot(session, auth.organization_id)
    return JSONResponse(
        {
            "schemaVersion": 1,
            "resourceId": auth.organization_id,
            "resourceType": "usage",
            "data": data,
            "nextCursor": None,
        }
    )


@router.post("/artifacts/{artifact_id}:authorize-download")
def authorize_artifact_download(
    artifact_id: str,
    payload: MutationRequest,
    request: Request,
    auth: AuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    route = f"POST /v1/artifacts/{artifact_id}:authorize-download"
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
                expires_at = datetime.fromisoformat(
                    replay.response_body["data"]["expiresAt"].replace("Z", "+00:00")
                )
                authorization = replay_download_authorization(
                    session,
                    auth,
                    artifact_id,
                    object_store=request.app.state.object_store,
                    expires_at=expires_at,
                )
                replay_body = {
                    **replay.response_body,
                    "data": {
                        **replay.response_body["data"],
                        "downloadUrl": authorization.url,
                    },
                }
                return JSONResponse(
                    replay_body,
                    status_code=replay.response_status,
                    headers={
                        "Cache-Control": "no-store",
                        "Idempotency-Replayed": "true",
                    },
                )
            authorization = authorize_download(
                session,
                auth,
                artifact_id,
                object_store=request.app.state.object_store,
                request_id=request.state.request_id,
                ttl_seconds=request.app.state.settings.download_url_ttl_seconds,
            )
            response_body = {
                "schemaVersion": 1,
                "resourceId": artifact_id,
                "resourceType": "authorizeArtifactDownload",
                "data": {
                    "downloadUrl": authorization.url,
                    "expiresAt": authorization.expires_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                },
                "nextCursor": None,
            }
            store_user_idempotency(
                session,
                auth,
                route=route,
                key=idempotency_key,
                request_body=body,
                resource_id=artifact_id,
                response_body={
                    **response_body,
                    "data": {"expiresAt": response_body["data"]["expiresAt"]},
                },
            )
        return JSONResponse(
            response_body,
            headers={"Cache-Control": "no-store", "Idempotency-Replayed": "false"},
        )
    except ArtifactNotFound:
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="工件不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )
    except ArtifactUnavailable:
        return problem_response(
            status=503,
            code="artifact_unavailable",
            title="工件暂不可用",
            detail="工件元数据与私有对象存储尚未一致",
            instance=str(request.url.path),
            retryable=True,
            request_id=request.state.request_id,
        )
    except DownloadAuthorizationExpired:
        return problem_response(
            status=410,
            code="download_authorization_expired",
            title="下载链接已过期",
            detail="请使用新的幂等键重新生成下载链接",
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
