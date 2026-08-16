"""OIDC/local authentication adapter and tenant-scoped FastAPI dependency."""

from __future__ import annotations

import re
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, Header, Request
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.tenancy import (
    DEFAULT_LOCAL_SUBJECT,
    LOCAL_ISSUER,
    AuthenticationRejected,
    IdentityClaims,
    TenantContext,
    provision_identity,
)
from jwt import PyJWKClient

_DEV_SUBJECT = re.compile(r"^[A-Za-z0-9._:@-]{1,200}$")


class ApiAuthenticationError(RuntimeError):
    pass


class BearerTokenVerifier(Protocol):
    def verify(self, token: str) -> IdentityClaims: ...


class OidcTokenVerifier:
    """Validate an OIDC JWT against an explicitly configured RSA JWKS."""

    def __init__(self, settings: DomainSettings) -> None:
        self._settings = settings
        self._jwks = PyJWKClient(
            settings.oidc_jwks_url,
            cache_keys=True,
            max_cached_keys=16,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def verify(self, token: str) -> IdentityClaims:
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=list(self._settings.oidc_algorithms),
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                leeway=self._settings.oidc_clock_skew_seconds,
                options={
                    "require": ["iss", "sub", "aud", "iat", "exp"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as error:
            raise ApiAuthenticationError("bearer token is invalid") from error
        subject = str(claims.get("sub") or "")
        if not subject:
            raise ApiAuthenticationError("bearer token subject is missing")
        return IdentityClaims(
            issuer=str(claims["iss"]),
            subject=subject,
            email=(str(claims["email"]) if claims.get("email") else None),
            display_name=str(claims.get("name") or claims.get("preferred_username") or "OIDC user"),
        )


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise ApiAuthenticationError("bearer authorization is required")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise ApiAuthenticationError("bearer authorization is malformed")
    return token.strip()


def _local_claims(subject: str | None, email: str | None, name: str | None) -> IdentityClaims:
    resolved_subject = subject or DEFAULT_LOCAL_SUBJECT
    if not _DEV_SUBJECT.fullmatch(resolved_subject):
        raise ApiAuthenticationError("local subject contains unsupported characters")
    resolved_email = email.strip() if email else f"{resolved_subject}@local.invalid"
    return IdentityClaims(
        issuer=LOCAL_ISSUER,
        subject=resolved_subject,
        email=resolved_email,
        display_name=(name or resolved_subject).strip()[:160] or "Local user",
    )


def require_auth(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
    dev_subject: Annotated[str | None, Header(alias="X-Dev-User-Subject")] = None,
    dev_email: Annotated[str | None, Header(alias="X-Dev-User-Email")] = None,
    dev_name: Annotated[str | None, Header(alias="X-Dev-User-Name")] = None,
) -> TenantContext:
    settings: DomainSettings = request.app.state.settings
    if settings.auth_mode == "local":
        if settings.app_environment not in {"local", "test"}:
            raise ApiAuthenticationError("local authentication is disabled")
        claims = _local_claims(dev_subject, dev_email, dev_name)
    else:
        verifier: BearerTokenVerifier = request.app.state.token_verifier
        claims = verifier.verify(_bearer_token(authorization))
    try:
        with request.app.state.session_factory.begin() as session:
            context = provision_identity(
                session,
                claims,
                requested_organization_id=organization_id,
            )
    except AuthenticationRejected as error:
        raise ApiAuthenticationError(str(error)) from error
    request.state.auth_context = context
    return context


AuthDependency = Annotated[TenantContext, Depends(require_auth)]
