"""FastAPI application factory with request, identity, and tenant boundaries."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.tenancy import TenantNotFound
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_api.auth import ApiAuthenticationError, OidcTokenVerifier
from instant_ppt_api.g03_routes import router as g03_router
from instant_ppt_api.g04_routes import router as g04_router
from instant_ppt_api.object_store import MinioPrivateObjectStore, ObjectStoreSettings
from instant_ppt_api.problems import problem_response
from instant_ppt_api.routes import router

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_logger = logging.getLogger("instant_ppt_api.request")


def create_app(
    *,
    settings: DomainSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    token_verifier: Any | None = None,
    object_store: Any | None = None,
) -> FastAPI:
    """Create the API with injectable persistence for integration tests."""
    resolved_settings = settings or DomainSettings.from_env()
    resolved_factory = session_factory or create_session_factory(
        create_domain_engine(resolved_settings.database_url)
    )
    application = FastAPI(title="即刻AI-PPT API", version="0.0.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Dev-User-Email",
            "X-Dev-User-Name",
            "X-Dev-User-Subject",
            "X-Organization-ID",
            "X-Request-ID",
        ],
        expose_headers=["Idempotency-Replayed", "Location", "X-Request-ID"],
        max_age=600,
    )
    application.state.settings = resolved_settings
    application.state.session_factory = resolved_factory
    application.state.token_verifier = token_verifier or (
        OidcTokenVerifier(resolved_settings)
        if resolved_settings.auth_mode == "oidc"
        else None
    )
    application.state.object_store = object_store or MinioPrivateObjectStore(
        ObjectStoreSettings.from_env()
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if _REQUEST_ID.fullmatch(supplied) else new_ulid()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        context = getattr(request.state, "auth_context", None)
        _logger.info(
            "request_completed method=%s path=%s status=%s request_id=%s organization_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            context.organization_id if context else "anonymous",
        )
        return response

    @application.exception_handler(ApiAuthenticationError)
    async def authentication_error(request: Request, _: ApiAuthenticationError):
        return problem_response(
            status=401,
            code="authentication_required",
            title="需要登录",
            detail="身份凭据缺失、无效或已过期",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )

    @application.exception_handler(TenantNotFound)
    async def tenant_not_found(request: Request, _: TenantNotFound):
        return problem_response(
            status=404,
            code="not_found",
            title="资源不存在",
            detail="组织不存在或无权访问",
            instance=str(request.url.path),
            request_id=request.state.request_id,
        )

    application.include_router(router)
    application.include_router(g03_router)
    application.include_router(g04_router)
    return application


app = create_app()
