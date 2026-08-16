from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from instant_ppt_domain.fake_worker import process_fake_job
from instant_ppt_domain.service import SYNTHETIC_ORGANIZATION_ID, get_job
from sqlalchemy.orm import Session, sessionmaker

from .helpers import create_job


def test_http_idempotency_and_snapshot(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    payload = {
        "schemaVersion": 1,
        "data": {"slideCount": 2, "failureModes": {}},
        "baseRevisionId": None,
    }
    headers = {"Idempotency-Key": "http-same-key"}
    first = client.post(
        "/v1/drafts/01ARZ3NDEKTSV4RRFFQ69G5FAC/generation-jobs",
        json=payload,
        headers=headers,
    )
    replay = client.post(
        "/v1/drafts/01ARZ3NDEKTSV4RRFFQ69G5FAC/generation-jobs",
        json=payload,
        headers=headers,
    )
    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    assert replay.headers["idempotency-replayed"] == "true"
    job_id = first.json()["resourceId"]
    assert process_fake_job(session_factory, job_id, "http-worker") == "succeeded"
    snapshot = client.get(f"/v1/jobs/{job_id}")
    assert snapshot.status_code == 200
    assert snapshot.json()["data"]["status"] == "succeeded"


@pytest.mark.parametrize("iteration", range(10))
def test_sse_resume(
    client: TestClient,
    session_factory: sessionmaker[Session],
    iteration: int,
) -> None:
    job_id = create_job(session_factory, key=f"sse-{iteration}", slide_count=2)
    assert process_fake_job(session_factory, job_id, f"sse-worker-{iteration}") == "succeeded"
    with session_factory() as session:
        latest_seq = get_job(session, job_id, SYNTHETIC_ORGANIZATION_ID).latest_seq
    response = client.get(f"/v1/jobs/{job_id}/events", headers={"Last-Event-ID": "2"})
    assert response.status_code == 200
    ids = [int(value) for value in re.findall(r"(?m)^id: (\d+)$", response.text)]
    assert ids == list(range(3, latest_seq + 1))
    assert len(ids) == len(set(ids))


def test_sse_unknown_sequence_returns_reset(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    job_id = create_job(session_factory, key="sse-reset", slide_count=1)
    assert process_fake_job(session_factory, job_id, "sse-reset-worker") == "succeeded"
    response = client.get(f"/v1/jobs/{job_id}/events", headers={"Last-Event-ID": "99999"})
    assert response.status_code == 200
    assert "event: reset" in response.text
    assert "sequence_unavailable" in response.text
