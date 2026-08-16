from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    GenerationJob,
    GenerationPublication,
    GenerationSnapshot,
    Presentation,
    PresentationRevision,
    SlideVersion,
    UsageLedger,
)
from instant_ppt_worker.generation_pipeline import process_generation_job
from instant_ppt_worker.source_pipeline import WorkerObjectSettings, WorkerObjectStore
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

ALICE = {"X-Dev-User-Subject": "g06-alice", "X-Dev-User-Name": "Alice"}
BOB = {"X-Dev-User-Subject": "g06-bob", "X-Dev-User-Name": "Bob"}


class MemoryGenerationStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_count = 0

    def put_file(self, object_key: str, path: Path, media_type: str) -> None:
        del media_type
        payload = path.read_bytes()
        if object_key in self.objects:
            previous = self.objects[object_key]
            if previous != payload and path.suffix == ".zip":
                with zipfile.ZipFile(io.BytesIO(previous)) as old_archive:
                    old_hashes = {
                        name: hashlib.sha256(old_archive.read(name)).hexdigest()
                        for name in old_archive.namelist()
                    }
                with zipfile.ZipFile(io.BytesIO(payload)) as new_archive:
                    new_hashes = {
                        name: hashlib.sha256(new_archive.read(name)).hexdigest()
                        for name in new_archive.namelist()
                    }
                assert old_hashes == new_hashes
            assert previous == payload
        self.objects[object_key] = payload
        self.put_count += 1


class MinioGenerationStore(MemoryGenerationStore):
    def __init__(self) -> None:
        super().__init__()
        self.real = WorkerObjectStore(WorkerObjectSettings.from_env())

    def put_file(self, object_key: str, path: Path, media_type: str) -> None:
        super().put_file(object_key, path, media_type)
        self.real.put_file(object_key, path, media_type)

    def cleanup(self) -> None:
        for object_key in self.objects:
            self.real.client.remove_object(self.real.bucket, object_key)


@pytest.fixture
def minio_store() -> MinioGenerationStore:
    store = MinioGenerationStore()
    yield store
    store.cleanup()


def _mutation(data: dict[str, Any], base: str | None = None) -> dict[str, Any]:
    return {"schemaVersion": 1, "data": data, "baseRevisionId": base}


def _approved_draft(client: TestClient, *, slide_count: int = 2) -> dict[str, Any]:
    draft_response = client.post(
        "/v1/drafts",
        headers={**ALICE, "Idempotency-Key": f"draft-{new_ulid()}"},
        json=_mutation({"topic": "G06 真实生成验证", "mode": "native"}),
    )
    assert draft_response.status_code == 201, draft_response.text
    draft = draft_response.json()["data"]
    intent_response = client.post(
        f"/v1/drafts/{draft['draftId']}/intent:infer",
        headers={**ALICE, "Idempotency-Key": f"intent-{draft['draftId']}"},
        json=_mutation({"language": "zh-CN"}),
    )
    assert intent_response.status_code == 201, intent_response.text
    slides = [
        {
            "outlineSlideId": new_ulid(),
            "type": "cover" if index == 0 else "content",
            "title": "增长结论" if index == 0 else f"执行路径 {index}",
            "keyPoints": ["结论先行", f"稳定页面 {index + 1}"],
            "sourceCitations": [],
        }
        for index in range(slide_count)
    ]
    outline_response = client.post(
        f"/v1/drafts/{draft['draftId']}/outline-revisions",
        headers={**ALICE, "Idempotency-Key": f"outline-{draft['draftId']}"},
        json=_mutation(
            {
                "storySummary": "从核心判断到执行路径",
                "targetSlideCount": 4,
                "slides": slides,
                "operation": "edit",
            }
        ),
    )
    assert outline_response.status_code == 201, outline_response.text
    outline = outline_response.json()["data"]
    approval_response = client.post(
        f"/v1/outline-revisions/{outline['outlineRevisionId']}:approve",
        headers={**ALICE, "Idempotency-Key": f"approve-{outline['outlineRevisionId']}"},
        json=_mutation({}),
    )
    assert approval_response.status_code == 200, approval_response.text
    return {"draft": draft, "outline": outline, "approval": approval_response.json()["data"]}


def _create_job(
    client: TestClient,
    draft_id: str,
    *,
    failure_modes: dict[int, str] | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/v1/drafts/{draft_id}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": f"generation-{draft_id}"},
        json=_mutation({"failureModes": failure_modes or {}}),
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["processor"] == "real"
    return response.json()["data"]


def test_real_generation_crash_replay_publishes_one_immutable_revision(
    client: TestClient,
    session_factory: sessionmaker[Session],
    minio_store: MinioGenerationStore,
) -> None:
    approved = _approved_draft(client)
    created = _create_job(client, approved["draft"]["draftId"])
    job_id = created["jobId"]
    replayed = _create_job(client, approved["draft"]["draftId"])
    assert replayed["jobId"] == job_id

    changed = {**approved["outline"], "slides": [dict(x) for x in approved["outline"]["slides"]]}
    changed["slides"][0] = {**changed["slides"][0], "title": "批准后不应进入快照"}
    changed_response = client.post(
        f"/v1/drafts/{approved['draft']['draftId']}/outline-revisions",
        headers={**ALICE, "Idempotency-Key": "post-approval-change"},
        json=_mutation(
            {
                "storySummary": changed["storySummary"],
                "targetSlideCount": changed["targetSlideCount"],
                "slides": changed["slides"],
                "operation": "edit",
            },
            approved["outline"]["outlineRevisionId"],
        ),
    )
    assert changed_response.status_code == 201

    store = minio_store
    with pytest.raises(RuntimeError, match="after upload"):
        process_generation_job(
            session_factory,
            job_id,
            "worker-crash-replay",
            organization_id=created["organizationId"],
            object_store=store,
            before_publish_callback=lambda: (_ for _ in ()).throw(
                RuntimeError("after upload before database publication")
            ),
        )
    with session_factory() as session:
        assert session.scalar(select(func.count(Artifact.id))) == 0
        assert session.scalar(select(func.count(Presentation.id))) == 0
        snapshot = session.get(GenerationSnapshot, created["snapshotId"])
        assert snapshot is not None
        assert snapshot.payload["outline"]["slides"][0]["title"] == "增长结论"

    assert (
        process_generation_job(
            session_factory,
            job_id,
            "worker-crash-replay",
            organization_id=created["organizationId"],
            object_store=store,
        )
        == "succeeded"
    )
    assert (
        process_generation_job(
            session_factory,
            job_id,
            "duplicate-delivery",
            organization_id=created["organizationId"],
            object_store=store,
        )
        == "noop_terminal"
    )

    response = client.get(f"/v1/jobs/{job_id}", headers=ALICE)
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "succeeded"
    assert payload["presentation"]["status"] == "ready"
    assert payload["publicationVersion"] == 1
    assert len(payload["artifacts"]) == 7
    assert client.get(f"/v1/jobs/{job_id}", headers=BOB).status_code == 404

    with session_factory() as session:
        artifacts = list(session.scalars(select(Artifact).order_by(Artifact.artifact_type)))
        assert len(artifacts) == 7
        for artifact in artifacts:
            content = store.objects[artifact.object_key]
            assert hashlib.sha256(content).hexdigest() == artifact.sha256
            assert len(content) == artifact.size_bytes
        baseline = next(x for x in artifacts if x.artifact_type == "generation_baseline_pptx")
        with zipfile.ZipFile(io.BytesIO(store.objects[baseline.object_key])) as package:
            assert "ppt/presentation.xml" in package.namelist()
            assert (
                len(
                    [
                        x
                        for x in package.namelist()
                        if x.startswith("ppt/slides/slide") and x.endswith(".xml")
                    ]
                )
                == 2
            )
        assert session.scalar(select(func.count(GenerationPublication.id))) == 1
        assert session.scalar(select(func.count(PresentationRevision.id))) == 1
        assert session.scalar(select(func.count(SlideVersion.id))) == 2
        metrics = dict(
            session.execute(
                select(UsageLedger.metric, func.sum(UsageLedger.quantity))
                .where(UsageLedger.job_id == job_id)
                .group_by(UsageLedger.metric)
            ).all()
        )
        assert metrics["slides"] == 2
        assert metrics["images"] == 0

    immutable_updates = (
        ("UPDATE generation_snapshots SET mode_id='visual' WHERE id=:id", created["snapshotId"]),
        (
            "UPDATE generation_publications SET version=2 WHERE job_id=:id",
            job_id,
        ),
        (
            "DELETE FROM presentation_revisions WHERE generation_job_id=:id",
            job_id,
        ),
    )
    for statement, identifier in immutable_updates:
        with session_factory() as session, pytest.raises(DBAPIError, match="immutable"):
            session.execute(text(statement), {"id": identifier})
            session.commit()


def test_killed_worker_is_reclaimed_without_duplicate_publish_or_billing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    database_url: str,
    minio_store: MinioGenerationStore,
) -> None:
    approved = _approved_draft(client, slide_count=1)
    created = _create_job(client, approved["draft"]["draftId"])
    with session_factory.begin() as session:
        job = session.get(GenerationJob, created["jobId"])
        assert job is not None
        job.test_behavior = {"crashOnceAtPosition": 1}

    result = subprocess.run(
        [
            sys.executable,
            "scripts/g06/crash_generation_worker.py",
            "--database-url",
            database_url,
            "--job-id",
            created["jobId"],
            "--organization-id",
            created["organizationId"],
        ],
        check=False,
        timeout=30,
    )
    assert result.returncode == 73
    with session_factory.begin() as session:
        job = session.get(GenerationJob, created["jobId"])
        assert job is not None and job.status == "running"
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "g06-replacement-worker",
            organization_id=created["organizationId"],
            object_store=minio_store,
        )
        == "succeeded"
    )
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "g06-duplicate-delivery",
            organization_id=created["organizationId"],
            object_store=minio_store,
        )
        == "noop_terminal"
    )
    with session_factory() as session:
        assert session.scalar(select(func.count(GenerationPublication.id))) == 1
        assert session.scalar(select(func.count(PresentationRevision.id))) == 1
        assert (
            session.scalar(
                select(func.sum(UsageLedger.quantity)).where(
                    UsageLedger.job_id == created["jobId"],
                    UsageLedger.metric == "slides",
                )
            )
            == 1
        )


def test_partial_retry_preserves_ready_artifact_and_creates_revision_two(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    approved = _approved_draft(client)
    created = _create_job(
        client,
        approved["draft"]["draftId"],
        failure_modes={2: "once"},
    )
    store = MemoryGenerationStore()
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "partial-worker",
            organization_id=created["organizationId"],
            object_store=store,
        )
        == "partially_succeeded"
    )
    first = client.get(f"/v1/jobs/{created['jobId']}", headers=ALICE).json()["data"]
    failed = next(slide for slide in first["slides"] if slide["status"] == "failed")
    ready = next(slide for slide in first["slides"] if slide["status"] == "ready")
    first_ready_artifact = next(
        item for item in first["artifacts"] if item["slideId"] == ready["slideId"]
    )
    retry = client.post(
        f"/v1/jobs/{created['jobId']}/slides/{failed['slideId']}:retry",
        headers={**ALICE, "Idempotency-Key": "retry-failed-slide"},
        json=_mutation({}),
    )
    assert retry.status_code == 202, retry.text
    retry_replay = client.post(
        f"/v1/jobs/{created['jobId']}/slides/{failed['slideId']}:retry",
        headers={**ALICE, "Idempotency-Key": "retry-failed-slide"},
        json=_mutation({}),
    )
    assert retry_replay.status_code == 202
    assert retry_replay.headers["Idempotency-Replayed"] == "true"
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "retry-worker",
            organization_id=created["organizationId"],
            object_store=store,
        )
        == "succeeded"
    )
    second = client.get(f"/v1/jobs/{created['jobId']}", headers=ALICE).json()["data"]
    assert second["publicationVersion"] == 2
    assert all(slide["status"] == "ready" for slide in second["slides"])
    with session_factory() as session:
        revisions = list(
            session.scalars(
                select(PresentationRevision)
                .where(PresentationRevision.generation_job_id == created["jobId"])
                .order_by(PresentationRevision.revision_number)
            )
        )
        assert [revision.partial for revision in revisions] == [True, False]
        second_ready = session.scalar(
            select(SlideVersion).where(
                SlideVersion.presentation_revision_id == revisions[1].id,
                SlideVersion.slide_id == ready["slideId"],
            )
        )
        assert second_ready is not None
        assert second_ready.artifact_id == first_ready_artifact["artifactId"]
        assert (
            session.scalar(
                select(func.sum(UsageLedger.quantity)).where(
                    UsageLedger.job_id == created["jobId"],
                    UsageLedger.metric == "slides",
                )
            )
            == 2
        )


def test_cancelled_generation_publishes_no_presentation(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    approved = _approved_draft(client, slide_count=1)
    created = _create_job(client, approved["draft"]["draftId"])
    cancel = client.post(
        f"/v1/jobs/{created['jobId']}:cancel",
        headers={**ALICE, "Idempotency-Key": "cancel-before-start"},
        json=_mutation({}),
    )
    assert cancel.status_code == 202
    cancel_replay = client.post(
        f"/v1/jobs/{created['jobId']}:cancel",
        headers={**ALICE, "Idempotency-Key": "cancel-before-start"},
        json=_mutation({}),
    )
    assert cancel_replay.status_code == 202
    assert cancel_replay.headers["Idempotency-Replayed"] == "true"
    store = MemoryGenerationStore()
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "cancel-worker",
            organization_id=created["organizationId"],
            object_store=store,
        )
        == "cancelled"
    )
    with session_factory() as session:
        job = session.get(GenerationJob, created["jobId"])
        assert job is not None and job.status == "cancelled"
        assert session.scalar(select(func.count(Presentation.id))) == 0
        assert session.scalar(select(func.count(Artifact.id))) == 0
    assert store.objects == {}


def test_cancel_wins_upload_publish_race_without_half_publication(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    approved = _approved_draft(client, slide_count=1)
    created = _create_job(client, approved["draft"]["draftId"])
    store = MemoryGenerationStore()

    def cancel_after_upload() -> None:
        response = client.post(
            f"/v1/jobs/{created['jobId']}:cancel",
            headers={**ALICE, "Idempotency-Key": "cancel-before-publish"},
            json=_mutation({}),
        )
        assert response.status_code == 202, response.text

    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "publish-race-worker",
            organization_id=created["organizationId"],
            object_store=store,
            before_publish_callback=cancel_after_upload,
        )
        == "cancelled"
    )
    assert store.objects
    with session_factory() as session:
        job = session.get(GenerationJob, created["jobId"])
        assert job is not None and job.status == "cancelled"
        assert session.scalar(select(func.count(Artifact.id))) == 0
        assert session.scalar(select(func.count(GenerationPublication.id))) == 0
        assert session.scalar(select(func.count(Presentation.id))) == 0


def test_redis_restart_sse_replays_postgres_events_and_hides_tenant(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    approved = _approved_draft(client, slide_count=1)
    created = _create_job(client, approved["draft"]["draftId"])
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "redis-replay-worker",
            organization_id=created["organizationId"],
            object_store=MemoryGenerationStore(),
        )
        == "succeeded"
    )
    subprocess.run(
        ["docker", "compose", "restart", "redis"],
        check=True,
        timeout=30,
    )
    redis_client = Redis.from_url("redis://localhost:6379/14")
    for _ in range(100):
        try:
            if redis_client.ping():
                break
        except Exception:  # pragma: no cover - bounded infrastructure polling
            time.sleep(0.1)
    else:  # pragma: no cover - emits a useful integration failure
        pytest.fail("Redis did not recover after container restart")
    redis_client.close()

    replay = client.get(
        f"/v1/jobs/{created['jobId']}/events",
        headers={**ALICE, "Last-Event-ID": "1"},
    )
    assert replay.status_code == 200
    assert "text/event-stream" in replay.headers["content-type"]
    assert "event: job.completed" in replay.text
    assert f'"jobId":"{created["jobId"]}"' in replay.text
    assert (
        client.get(f"/v1/jobs/{created['jobId']}/events", headers=BOB).status_code
        == 404
    )


def test_quota_and_cross_tenant_rejection_create_no_job(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    approved = _approved_draft(client)
    draft_id = approved["draft"]["draftId"]
    with session_factory.begin() as session:
        organization_id = session.execute(
            text("SELECT organization_id FROM drafts WHERE id=:id"), {"id": draft_id}
        ).scalar_one()
        session.execute(
            text(
                "UPDATE entitlements SET monthly_slide_limit=1 "
                "WHERE organization_id=:organization_id"
            ),
            {"organization_id": organization_id},
        )
    quota = client.post(
        f"/v1/drafts/{draft_id}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": "quota-rejected"},
        json=_mutation({}),
    )
    assert quota.status_code == 429
    assert quota.json()["code"] == "quota_exceeded"
    foreign = client.post(
        f"/v1/drafts/{draft_id}/generation-jobs",
        headers={**BOB, "Idempotency-Key": "foreign-rejected"},
        json=_mutation({}),
    )
    assert foreign.status_code == 404
    with session_factory() as session:
        assert session.scalar(select(func.count(GenerationJob.id))) == 0
