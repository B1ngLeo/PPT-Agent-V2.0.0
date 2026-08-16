from __future__ import annotations

import pytest
from instant_ppt_domain.artifacts import tenant_object_key
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.tenancy import sanitize_audit_details


def _settings(**overrides: object) -> DomainSettings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://test:test@localhost/test",
        "redis_events_url": "redis://localhost/0",
        "celery_broker_url": "redis://localhost/1",
        "sse_heartbeat_seconds": 20,
        "outbox_poll_seconds": 0.25,
        "worker_lease_seconds": 30,
    }
    values.update(overrides)
    return DomainSettings(**values)  # type: ignore[arg-type]


def test_production_cannot_enable_local_authentication() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        _settings(app_environment="production", auth_mode="local")


def test_oidc_requires_complete_strict_configuration() -> None:
    with pytest.raises(ValueError, match="issuer, audience, and JWKS"):
        _settings(auth_mode="oidc")
    with pytest.raises(ValueError, match="RSA"):
        _settings(
            auth_mode="oidc",
            oidc_issuer="https://issuer.example/",
            oidc_audience="instant-ppt-api",
            oidc_jwks_url="https://issuer.example/jwks.json",
            oidc_algorithms=("HS256",),
        )


def test_tenant_object_key_has_no_user_filename_or_traversal() -> None:
    organization_id = "01ARZ3NDEKTSV4RRFFQ69G5FAA"
    artifact_id = "01ARZ3NDEKTSV4RRFFQ69G5FAX"
    assert tenant_object_key(organization_id, "published", artifact_id) == (
        f"tenants/{organization_id}/published/{artifact_id}"
    )
    with pytest.raises(ValueError):
        tenant_object_key(organization_id, "public", artifact_id)
    with pytest.raises(ValueError):
        tenant_object_key("../foreign-tenant", "published", artifact_id)


def test_audit_details_drop_credentials_urls_and_content() -> None:
    details = sanitize_audit_details(
        {
            "authorization": "Bearer secret",
            "downloadUrl": "https://signed.example/?secret=yes",
            "sourceContent": "confidential body",
            "status": "denied",
            "count": 2,
        }
    )
    assert details == {"status": "denied", "count": 2}
