from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from instant_ppt_domain.fake_worker import process_fake_job
from instant_ppt_domain.models import AuditLog, Entitlement, Membership, Organization, User
from instant_ppt_domain.service import ResourceNotFound
from instant_ppt_domain.tenancy import IdentityClaims, provision_identity
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .helpers import identity_headers


def test_concurrent_first_login_creates_one_personal_organization(
    session_factory: sessionmaker[Session],
) -> None:
    claims = IdentityClaims(
        issuer="urn:instant-ppt:local",
        subject="concurrent-user",
        email="same@example.test",
        display_name="Concurrent User",
    )

    def login(_: int) -> str:
        with session_factory.begin() as session:
            return provision_identity(session, claims).organization_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        organization_ids = list(executor.map(login, range(8)))
    assert len(set(organization_ids)) == 1
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(Organization)) == 1
        assert session.scalar(select(func.count()).select_from(Membership)) == 1
        assert session.scalar(select(func.count()).select_from(Entitlement)) == 1


def test_entitlements_usage_and_cross_tenant_api_sse_denial(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    alice_headers = identity_headers("alice")
    bob_headers = identity_headers("bob")
    alice_entitlements = client.get("/v1/me/entitlements", headers=alice_headers)
    bob_entitlements = client.get("/v1/me/entitlements", headers=bob_headers)
    assert alice_entitlements.status_code == bob_entitlements.status_code == 200
    alice_org = alice_entitlements.json()["resourceId"]
    bob_org = bob_entitlements.json()["resourceId"]
    assert alice_org != bob_org
    assert alice_entitlements.json()["data"] == {
        "planCode": "p1-default",
        "maxSlidesPerDeck": 30,
        "monthlySlideLimit": 300,
        "maxImagesPerDeck": 1,
        "monthlyImageLimit": 30,
        "monthlyImageCostLimitMicrounits": 3000000,
        "maxConcurrentJobs": 1,
        "allowedModes": ["native"],
        "effectiveFrom": alice_entitlements.json()["data"]["effectiveFrom"],
        "effectiveUntil": None,
    }
    usage = client.get("/v1/me/usage", headers=alice_headers)
    assert usage.status_code == 200
    assert usage.json()["data"]["metrics"]["images"] == 0

    response = client.post(
        "/v1/drafts/01ARZ3NDEKTSV4RRFFQ69G5FAF/generation-jobs",
        headers={**alice_headers, "Idempotency-Key": "alice-job"},
        json={"schemaVersion": 1, "data": {"slideCount": 1}},
    )
    assert response.status_code == 202
    job_id = response.json()["resourceId"]

    assert client.get(f"/v1/jobs/{job_id}", headers=bob_headers).status_code == 404
    assert (
        client.get(f"/v1/jobs/{job_id}/events", headers=bob_headers).status_code == 404
    )
    assert (
        client.get(
            "/v1/me/entitlements",
            headers={**bob_headers, "X-Organization-ID": alice_org},
        ).status_code
        == 404
    )
    unknown = client.get(
        "/v1/jobs/01ARZ3NDEKTSV4RRFFQ69G5FZZ", headers=bob_headers
    )
    denied = client.get(f"/v1/jobs/{job_id}", headers=bob_headers)
    assert unknown.status_code == denied.status_code == 404
    assert unknown.json()["code"] == denied.json()["code"] == "not_found"

    with pytest.raises(ResourceNotFound):
        process_fake_job(
            session_factory,
            job_id,
            "malicious-worker",
            organization_id=bob_org,
        )
    assert (
        process_fake_job(
            session_factory,
            job_id,
            "authorized-worker",
            organization_id=alice_org,
        )
        == "succeeded"
    )
    with session_factory() as session:
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.organization_id == alice_org,
                AuditLog.action == "generation_job.created",
            )
        )
        assert audit is not None
        assert audit.resource_id == job_id
        assert audit.actor_id != ""
        assert audit.request_id != ""


def test_disabled_user_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    headers = identity_headers("disabled-user")
    assert client.get("/v1/me/entitlements", headers=headers).status_code == 200
    with session_factory.begin() as session:
        user = session.scalar(select(User).where(User.subject == "disabled-user"))
        assert user is not None
        user.status = "disabled"
    denied = client.get("/v1/me/entitlements", headers=headers)
    assert denied.status_code == 401
    assert denied.json()["code"] == "authentication_required"
