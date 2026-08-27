from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from instant_ppt_domain.models import PlanningJob
from instant_ppt_worker.planning_pipeline import (
    DeterministicPlanningExecutor,
    RetryablePlanningFailure,
    process_planning_job,
)
from instant_ppt_worker.providers import ProviderRequestError
from sqlalchemy.orm import Session, sessionmaker

ALICE = {"X-Dev-User-Subject": "g06-planning", "X-Dev-User-Name": "Planner"}
BOB = {"X-Dev-User-Subject": "g06-planning-bob", "X-Dev-User-Name": "Bob"}


def _mutation(data: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": 1, "data": data, "baseRevisionId": None}


class TimeoutThenSuccessExecutor:
    def __init__(self) -> None:
        self.calls = 0
        self.delegate = DeterministicPlanningExecutor()

    def close(self) -> None:
        return None

    def infer_intent(
        self, *, topic: str, source_refs: list[str], language: str
    ) -> Any:
        self.calls += 1
        if self.calls == 1:
            raise ProviderRequestError(
                "qwen",
                None,
                None,
                failure_kind="ReadTimeout",
                upstream_code="provider_timeout",
                retryable=True,
            )
        return self.delegate.infer_intent(
            topic=topic,
            source_refs=source_refs,
            language=language,
        )

    def generate_outline(self, **kwargs: Any) -> Any:
        return self.delegate.generate_outline(**kwargs)


def test_planning_job_survives_retry_and_publishes_pollable_result(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    draft_response = client.post(
        "/v1/drafts",
        headers={**ALICE, "Idempotency-Key": "async-planning-draft"},
        json=_mutation({"topic": "Qwen 超时恢复验证", "mode": "native"}),
    )
    assert draft_response.status_code == 201, draft_response.text
    draft_id = draft_response.json()["data"]["draftId"]

    queued_response = client.post(
        f"/v1/drafts/{draft_id}/intent:infer",
        headers={**ALICE, "Idempotency-Key": "async-planning-intent"},
        json=_mutation({"language": "zh-CN"}),
    )
    assert queued_response.status_code == 202, queued_response.text
    queued = queued_response.json()["data"]
    job_id = queued["planningJobId"]
    assert queued["status"] == "queued"
    assert queued["attempt"] == 0
    assert queued_response.headers["Location"] == f"/v1/planning-jobs/{job_id}"

    replay = client.post(
        f"/v1/drafts/{draft_id}/intent:infer",
        headers={**ALICE, "Idempotency-Key": "async-planning-intent"},
        json=_mutation({"language": "zh-CN"}),
    )
    assert replay.status_code == 202
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["data"]["planningJobId"] == job_id
    assert client.get(f"/v1/planning-jobs/{job_id}", headers=BOB).status_code == 404

    with session_factory() as session:
        job = session.get(PlanningJob, job_id)
        assert job is not None
        organization_id = job.organization_id

    executor = TimeoutThenSuccessExecutor()
    with pytest.raises(RetryablePlanningFailure, match="provider_timeout"):
        process_planning_job(
            session_factory,
            job_id,
            organization_id,
            executor=executor,
        )

    retrying = client.get(f"/v1/planning-jobs/{job_id}", headers=ALICE)
    assert retrying.status_code == 200
    retrying_data = retrying.json()["data"]
    assert retrying_data["status"] == "retrying"
    assert retrying_data["attempt"] == 1
    assert retrying_data["retryable"] is True
    assert retrying_data["errorCode"] == "provider_timeout"
    assert retrying_data["result"] is None

    assert (
        process_planning_job(
            session_factory,
            job_id,
            organization_id,
            executor=executor,
        )
        == "succeeded"
    )
    completed = client.get(f"/v1/planning-jobs/{job_id}", headers=ALICE)
    assert completed.status_code == 200
    data = completed.json()["data"]
    assert data["status"] == "succeeded"
    assert data["attempt"] == 2
    assert data["terminal"] is True
    assert data["result"]["intentRevisionId"] == data["resultRevisionId"]

    restored = client.get(f"/v1/drafts/{draft_id}", headers=ALICE)
    assert restored.status_code == 200
    assert restored.json()["data"]["currentIntentRevisionId"] == data["resultRevisionId"]
