from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
import sys
import threading
import time
import zipfile
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    Draft,
    EffectiveDesignSpecRevision,
    GenerationJob,
    GenerationJobSlide,
    GenerationPublication,
    GenerationSnapshot,
    PlanningJob,
    Presentation,
    PresentationRevision,
    ProviderCall,
    SlideVersion,
    UsageLedger,
    UsageReservation,
    WorkflowCheckpointSet,
    WorkflowGateReceipt,
    WorkflowIntermediateArtifact,
    WorkflowRun,
    WorkflowStageAttempt,
)
from instant_ppt_worker.generation_pipeline import process_generation_job
from instant_ppt_worker.planning_pipeline import process_planning_job
from instant_ppt_worker.providers import GeneratedImage
from instant_ppt_worker.source_pipeline import WorkerObjectSettings, WorkerObjectStore
from PIL import Image
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

    def download(self, object_key: str, target: Path, *, max_bytes: int) -> str:
        from instant_ppt_worker.source_pipeline import SourceObjectError

        try:
            payload = self.objects[object_key]
        except KeyError as error:
            raise SourceObjectError("source object could not be downloaded") from error
        if len(payload) > max_bytes:
            raise SourceObjectError("source exceeds the download limit")
        target.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()


class FakeCoverImageProvider:
    provider_name = "fake-image"

    def __init__(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (1536, 1024), color=(24, 72, 128)).save(buffer, format="PNG")
        self.content = buffer.getvalue()
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        prompt: str,
        *,
        size: str | None = None,
        quality: str | None = None,
        idempotency_key: str | None = None,
    ) -> GeneratedImage:
        self.calls.append(
            {
                "promptPresent": bool(prompt),
                "size": size,
                "quality": quality,
                "idempotencyKey": idempotency_key,
            }
        )
        return GeneratedImage(self.content, "image/png", "gpt-image-2")


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
        f"/v1/drafts/{draft['draftId']}/intent-revisions",
        headers={**ALICE, "Idempotency-Key": f"intent-{draft['draftId']}"},
        json=_mutation(
            {
                "title": draft["title"],
                "audience": "测试用户",
                "goal": "验证生成链路",
                "targetSlideCount": 4,
                "language": "zh-CN",
                "contentDepth": "conclusion_first",
                "visualPreference": "data_first",
                "notes": "稳定的集成测试输入",
                "sourceRefs": [],
            }
        ),
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
        json=_mutation(
            {
                "failureModes": failure_modes or {},
                "continueLimitedDraft": True,
                "authorizeStrategistDesignLock": True,
            }
        ),
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["processor"] == "real"
    return response.json()["data"]


def test_generation_requires_explicit_strategist_design_lock_authorization(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    approved = _approved_draft(client)

    response = client.post(
        f"/v1/drafts/{approved['draft']['draftId']}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": "missing-design-authorization"},
        json=_mutation({"continueLimitedDraft": True}),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "generation_input_not_ready"
    assert "design and spec-lock authorization" in response.json()["detail"]
    with session_factory() as session:
        assert session.scalar(select(func.count(GenerationJob.id))) == 0


def test_selected_visual_style_is_frozen_into_generation_snapshot(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    approved = _approved_draft(client)
    draft_id = approved["draft"]["draftId"]
    approval_id = approved["approval"]["approvalId"]
    queued = client.post(
        f"/v1/drafts/{draft_id}/visual-styles:generate",
        headers={**ALICE, "Idempotency-Key": f"visual-{new_ulid()}"},
        json=_mutation({}, approval_id),
    )
    assert queued.status_code == 202, queued.text
    planning_job_id = queued.json()["data"]["planningJobId"]
    with session_factory() as session:
        planning_job = session.get(PlanningJob, planning_job_id)
        assert planning_job is not None
        organization_id = planning_job.organization_id
    assert process_planning_job(session_factory, planning_job_id, organization_id) == "succeeded"
    proposal = client.get(f"/v1/planning-jobs/{planning_job_id}", headers=ALICE).json()["data"][
        "result"
    ]
    selected = proposal["options"][1]

    generation = client.post(
        f"/v1/drafts/{draft_id}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": f"generation-style-{new_ulid()}"},
        json=_mutation(
            {
                "continueLimitedDraft": True,
                "authorizeStrategistDesignLock": True,
                "visualStylePlanningJobId": planning_job_id,
                "visualStyleOptionId": selected["id"],
            }
        ),
    )
    assert generation.status_code == 202, generation.text
    generation_job_id = generation.json()["data"]["jobId"]
    with session_factory() as session:
        job = session.get(GenerationJob, generation_job_id)
        assert job is not None
        snapshot = session.get(GenerationSnapshot, job.snapshot_id)
        assert snapshot is not None
        assert snapshot.payload["visualStyle"]["id"] == selected["id"]
        assert snapshot.payload["visualStyle"]["colors"] == selected["colors"]
        assert snapshot.payload["visualStyle"]["typography"] == selected["typography"]
        assert snapshot.payload["visualStyle"]["planningJobId"] == planning_job_id


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
        design_authorization = snapshot.payload["designAuthorization"]
        assert design_authorization["authorized"] is True
        assert design_authorization["scope"] == "strategist-design-and-lock"
        assert design_authorization["authorizedBy"] == approved["approval"]["approvedBy"]
        assert datetime.fromisoformat(
            design_authorization["authorizedAt"].replace("Z", "+00:00")
        ) >= datetime.fromisoformat(approved["approval"]["approvedAt"].replace("Z", "+00:00"))

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
    presentation_response = client.get(
        f"/v1/presentations/{payload['presentation']['presentationId']}", headers=ALICE
    )
    assert presentation_response.status_code == 200
    assert (
        presentation_response.json()["data"]["currentRevision"]["contentMode"]
        == "limited-general-draft"
    )
    assert payload["publicationVersion"] == 1
    assert len(payload["artifacts"]) == 14
    assert {
        "generation_design_spec",
        "generation_spec_lock",
        "generation_evidence_map",
        "generation_workflow_result",
        "generation_final_svg_qa",
        "generation_package_qa",
        "generation_visual_review",
    }.issubset({artifact["artifactType"] for artifact in payload["artifacts"]})
    assert client.get(f"/v1/jobs/{job_id}", headers=BOB).status_code == 404

    with session_factory() as session:
        artifacts = list(session.scalars(select(Artifact).order_by(Artifact.artifact_type)))
        assert len(artifacts) == 14
        run = session.scalar(select(WorkflowRun).where(WorkflowRun.generation_job_id == job_id))
        assert run is not None
        assert run.profile == "default-agentic"
        assert run.status == "succeeded"
        assert run.attempt == 2
        assert session.scalar(
            select(func.count(WorkflowStageAttempt.id)).where(
                WorkflowStageAttempt.workflow_run_id == run.id
            )
        )
        assert (
            session.scalar(
                select(func.count(WorkflowCheckpointSet.id)).where(
                    WorkflowCheckpointSet.workflow_run_id == run.id
                )
            )
            == 4
        )
        assert session.scalar(
            select(func.count(WorkflowGateReceipt.id)).where(
                WorkflowGateReceipt.workflow_run_id == run.id
            )
        )
        assert (
            session.scalar(
                select(func.count(WorkflowIntermediateArtifact.id)).where(
                    WorkflowIntermediateArtifact.workflow_run_id == run.id
                )
            )
            == 14
        )
        effective = session.scalar(
            select(EffectiveDesignSpecRevision).where(
                EffectiveDesignSpecRevision.workflow_run_id == run.id
            )
        )
        assert effective is not None
        assert effective.payload["wholeDeckFinalGate"] == "passed"
        for artifact in artifacts:
            content = store.objects[artifact.object_key]
            assert hashlib.sha256(content).hexdigest() == artifact.sha256
            assert len(content) == artifact.size_bytes
        generation_manifest = next(
            artifact for artifact in artifacts if artifact.artifact_type == "generation_manifest"
        )
        manifest_payload = json.loads(store.objects[generation_manifest.object_key])
        assert manifest_payload["contentMode"] == "limited-general-draft"
        assert manifest_payload["sourceGroundingStatus"] == "not-applicable-limited-draft"
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


def test_template_fallback_persists_disclosure_in_presentation_revision(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRESENTATION_AUTHORING_MODE", "deterministic-template")
    approved = _approved_draft(client, slide_count=1)
    created = _create_job(client, approved["draft"]["draftId"])
    assert created["authoringMode"] == "deterministic-template"
    assert created["fallbackReason"] == "operator-feature-flag"

    store = MemoryGenerationStore()
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "template-fallback-worker",
            organization_id=created["organizationId"],
            object_store=store,
        )
        == "succeeded"
    )

    job = client.get(f"/v1/jobs/{created['jobId']}", headers=ALICE).json()["data"]
    response = client.get(
        f"/v1/presentations/{job['presentation']['presentationId']}", headers=ALICE
    )
    assert response.status_code == 200, response.text
    revision = response.json()["data"]["currentRevision"]
    assert revision["engineProfile"] == "deterministic-template"
    assert revision["contentMode"] == "limited-general-draft"
    assert revision["authoringMode"] == "deterministic-template"
    assert revision["authoringDisclosure"] == "template-limited-editable-draft"
    assert revision["authoring"]["fallbackReason"] == "operator-feature-flag"
    assert revision["authoring"]["agentAuthoredPageCount"] == 0
    assert revision["authoring"]["templateAuthoredPageCount"] == 1
    assert revision["suggestedFilename"].endswith("-模板化受限初稿.pptx")

    with session_factory() as session:
        manifest_artifact = session.scalar(
            select(Artifact).where(Artifact.artifact_type == "generation_manifest")
        )
        assert manifest_artifact is not None
        manifest = json.loads(store.objects[manifest_artifact.object_key])
        assert manifest["authoring"]["mode"] == "deterministic-template"
        assert manifest["authoring"]["turnCount"] == 0
        assert manifest["suggestedFilename"].endswith("-模板化受限初稿.pptx")


def test_image_provider_environment_alone_cannot_enable_default_workflow_images(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("IMAGE_MAX_PER_DECK", "1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://frozen.example/v1")
    monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "low")
    approved = _approved_draft(client, slide_count=1)
    created = _create_job(client, approved["draft"]["draftId"])
    with session_factory() as session:
        snapshot = session.get(GenerationSnapshot, created["snapshotId"])
        assert snapshot is not None
        frozen = snapshot.payload["providerConfiguration"]["image"]
        assert frozen["enabled"] is True
        assert frozen["baseUrl"] == "https://frozen.example/v1"
        assert frozen["maxImagesPerDeck"] == 1
        assert snapshot.payload["engineProfile"] == "default-agentic"
        assert snapshot.payload["imagePolicy"] == {
            "scope": "none",
            "usage": ["none"],
            "notes": {},
        }

    monkeypatch.setenv("OPENAI_BASE_URL", "https://runtime-change.example/v1")
    provider = FakeCoverImageProvider()
    store = MemoryGenerationStore()
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "g06-image-worker",
            organization_id=created["organizationId"],
            object_store=store,
            image_provider=provider,
        )
        == "succeeded"
    )
    assert provider.calls == []

    with session_factory() as session:
        artifacts = list(
            session.scalars(
                select(Artifact).where(Artifact.organization_id == created["organizationId"])
            )
        )
        assert not any(
            artifact.artifact_type
            in {
                "generation_ai_cover_image",
                "generation_image_asset",
            }
            for artifact in artifacts
        )
        image_usage = session.scalar(
            select(func.sum(UsageLedger.quantity)).where(
                UsageLedger.job_id == created["jobId"],
                UsageLedger.metric == "images",
            )
        )
        assert image_usage == 0
        provider_call_count = session.execute(
            text(
                "SELECT count(*) FROM provider_calls WHERE draft_id = :draft_id "
                "AND purpose IN ('cover_image_generate', 'default_workflow_image_generate')"
            ),
            {"draft_id": approved["draft"]["draftId"]},
        ).scalar_one()
        assert provider_call_count == 0
        baseline = next(
            artifact
            for artifact in artifacts
            if artifact.artifact_type == "generation_baseline_pptx"
        )
        with zipfile.ZipFile(io.BytesIO(store.objects[baseline.object_key])) as package:
            media = [name for name in package.namelist() if name.startswith("ppt/media/")]
            assert media == []


def test_explicit_selective_image_policy_is_frozen_against_stable_slide_ids(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    approved = _approved_draft(client, slide_count=2)
    selected_outline_slide_id = approved["outline"]["slides"][0]["outlineSlideId"]
    response = client.post(
        f"/v1/drafts/{approved['draft']['draftId']}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": "explicit-selective-image-policy"},
        json=_mutation(
            {
                "continueLimitedDraft": True,
                "authorizeStrategistDesignLock": True,
                "imagePolicy": {
                    "scope": "selective",
                    "usage": ["ai"],
                    "notes": {selected_outline_slide_id: "non-evidentiary editorial hero"},
                    "aiPath": "manual",
                    "aiPathChain": ["manual"],
                },
            }
        ),
    )

    assert response.status_code == 202, response.text
    created = response.json()["data"]
    with session_factory() as session:
        snapshot = session.get(GenerationSnapshot, created["snapshotId"])
        assert snapshot is not None
        selected_slide_id = session.scalar(
            select(GenerationJobSlide.slide_id).where(
                GenerationJobSlide.job_id == created["jobId"],
                GenerationJobSlide.outline_slide_id == selected_outline_slide_id,
            )
        )
        assert selected_slide_id is not None
        assert snapshot.payload["engineProfile"] == "default-agentic"
        assert snapshot.payload["imagePolicy"] == {
            "scope": "selective",
            "usage": ["ai"],
            "notes": {selected_slide_id: "non-evidentiary editorial hero"},
            "aiPath": "manual",
            "aiPathChain": ["manual"],
            "providedAssets": [],
            "officeNativeFallbacks": [],
        }

    store = MemoryGenerationStore()
    assert (
        process_generation_job(
            session_factory,
            created["jobId"],
            "g06-image-needs-manual-worker",
            organization_id=created["organizationId"],
            object_store=store,
        )
        == "needs_manual"
    )
    with session_factory() as session:
        job = session.get(GenerationJob, created["jobId"])
        run = session.scalar(
            select(WorkflowRun).where(WorkflowRun.generation_job_id == created["jobId"])
        )
        assert job is not None and job.status == "failed"
        assert run is not None and run.status == "needs_manual"
        assert run.stage == "image_resources"
        assert session.scalar(
            select(func.count(WorkflowCheckpointSet.id)).where(
                WorkflowCheckpointSet.workflow_run_id == run.id
            )
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM provider_calls WHERE draft_id = :draft_id "
                    "AND purpose = 'default_workflow_image_generate' AND status = 'failed'"
                ),
                {"draft_id": approved["draft"]["draftId"]},
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(GenerationPublication.id)).where(
                    GenerationPublication.job_id == created["jobId"]
                )
            )
            == 0
        )
    assert store.objects == {}
    snapshot_response = client.get(f"/v1/jobs/{created['jobId']}", headers=ALICE)
    assert snapshot_response.status_code == 200
    workflow = snapshot_response.json()["data"]["workflow"]
    assert workflow["status"] == "needs_manual"
    assert workflow["stage"] == "image_resources"
    assert workflow["errorCode"] == "IMAGE_RESOURCE_NEEDS_MANUAL"
    assert "required image acquisition is unresolved" in workflow["recoveryAction"]


def test_explicit_api_image_is_published_audited_and_billed_once(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_bytes = FakeCoverImageProvider().content

    class ImageHandler(BaseHTTPRequestHandler):
        calls: list[dict[str, str]] = []

        def do_POST(self) -> None:  # noqa: N802
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size))
            self.__class__.calls.append(
                {
                    "path": self.path,
                    "model": str(payload.get("model")),
                    "outputFormat": str(payload.get("output_format")),
                }
            )
            body = json.dumps(
                {"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), ImageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("IMAGE_GENERATION_ENABLED", "true")
        monkeypatch.setenv("IMAGE_MAX_PER_DECK", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "local-test-only")
        monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-image-2")
        monkeypatch.setenv("OPENAI_OUTPUT_FORMAT", "png")
        monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "low")
        monkeypatch.setenv("IMAGE_COST_MICROUNITS", "123000")
        approved = _approved_draft(client, slide_count=1)
        response = client.post(
            f"/v1/drafts/{approved['draft']['draftId']}/generation-jobs",
            headers={**ALICE, "Idempotency-Key": "explicit-api-image-policy"},
            json=_mutation(
                {
                    "continueLimitedDraft": True,
                    "authorizeStrategistDesignLock": True,
                    "imagePolicy": {
                        "scope": "cover_only",
                        "usage": ["ai"],
                        "notes": {"cover": "non-evidentiary editorial hero"},
                        "aiPath": "api",
                        "aiPathChain": ["api", "manual"],
                    },
                }
            ),
        )
        assert response.status_code == 202, response.text
        created = response.json()["data"]
        store = MemoryGenerationStore()

        assert (
            process_generation_job(
                session_factory,
                created["jobId"],
                "g06-explicit-api-image-worker",
                organization_id=created["organizationId"],
                object_store=store,
            )
            == "succeeded"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert ImageHandler.calls == [
        {
            "path": "/v1/images/generations",
            "model": "gpt-image-2",
            "outputFormat": "png",
        }
    ]
    with session_factory() as session:
        artifacts = list(
            session.scalars(
                select(Artifact).where(Artifact.organization_id == created["organizationId"])
            )
        )
        by_type = {artifact.artifact_type: artifact for artifact in artifacts}
        assert {
            "generation_image_asset",
            "generation_image_analysis",
            "generation_image_audit",
            "generation_image_prompts",
        }.issubset(by_type)
        manifest = json.loads(store.objects[by_type["generation_manifest"].object_key])
        assert manifest["engineProfile"] == "default-agentic"
        assert manifest["imageGeneration"]["scope"] == "cover_only"
        assert manifest["imageGeneration"]["imageCount"] == 1
        assert manifest["imageGeneration"]["generatedCount"] == 1
        assert manifest["imageGeneration"]["costMicrounits"] == 123000
        assert (
            session.scalar(
                select(func.sum(UsageLedger.quantity)).where(
                    UsageLedger.job_id == created["jobId"],
                    UsageLedger.metric == "images",
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.sum(UsageLedger.quantity)).where(
                    UsageLedger.job_id == created["jobId"],
                    UsageLedger.metric == "image_cost_microunits",
                )
            )
            == 123000
        )
        reservation = session.scalar(
            select(UsageReservation).where(UsageReservation.job_id == created["jobId"])
        )
        assert reservation is not None
        assert reservation.status == "settled"
        assert reservation.reserved_images == reservation.settled_images == 1
        assert reservation.reserved_cost_microunits == reservation.settled_cost_microunits == 123000
        provider_call = session.execute(
            text(
                "SELECT provider, model, purpose, status, request_hash FROM provider_calls "
                "WHERE draft_id = :draft_id AND purpose = 'default_workflow_image_generate'"
            ),
            {"draft_id": approved["draft"]["draftId"]},
        ).one()
        assert provider_call[:4] == (
            "openai-image",
            "gpt-image-2",
            "default_workflow_image_generate",
            "succeeded",
        )
        assert len(provider_call.request_hash) == 64
        baseline = by_type["generation_baseline_pptx"]
        with zipfile.ZipFile(io.BytesIO(store.objects[baseline.object_key])) as package:
            assert any(name.startswith("ppt/media/") for name in package.namelist())


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
    assert client.get(f"/v1/jobs/{created['jobId']}/events", headers=BOB).status_code == 404


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
        json=_mutation(
            {
                "continueLimitedDraft": True,
                "authorizeStrategistDesignLock": True,
            }
        ),
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


def test_image_count_and_cost_quota_reject_before_job_or_provider_call(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    approved = _approved_draft(client, slide_count=1)
    draft_id = approved["draft"]["draftId"]
    image_policy = {
        "continueLimitedDraft": True,
        "authorizeStrategistDesignLock": True,
        "imagePolicy": {
            "scope": "cover_only",
            "usage": ["ai"],
            "notes": {"cover": "non-evidentiary hero"},
            "aiPath": "manual",
            "aiPathChain": ["manual"],
        },
    }
    with session_factory.begin() as session:
        organization_id = session.scalar(select(Draft.organization_id).where(Draft.id == draft_id))
        assert organization_id is not None
        session.execute(
            text(
                "UPDATE entitlements SET max_images_per_deck=0 "
                "WHERE organization_id=:organization_id"
            ),
            {"organization_id": organization_id},
        )
    per_deck = client.post(
        f"/v1/drafts/{draft_id}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": "image-per-deck-quota"},
        json=_mutation(image_policy),
    )
    assert per_deck.status_code == 429

    with session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE entitlements SET max_images_per_deck=1, monthly_image_limit=0 "
                "WHERE organization_id=:organization_id"
            ),
            {"organization_id": organization_id},
        )
    monthly = client.post(
        f"/v1/drafts/{draft_id}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": "image-monthly-quota"},
        json=_mutation(image_policy),
    )
    assert monthly.status_code == 429

    with session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE entitlements SET monthly_image_limit=1, "
                "monthly_image_cost_limit_microunits=1 "
                "WHERE organization_id=:organization_id"
            ),
            {"organization_id": organization_id},
        )
    cost = client.post(
        f"/v1/drafts/{draft_id}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": "image-cost-quota"},
        json=_mutation(image_policy),
    )
    assert cost.status_code == 429
    with session_factory() as session:
        assert session.scalar(select(func.count(GenerationJob.id))) == 0
        assert session.scalar(select(func.count(UsageReservation.id))) == 0
        assert (
            session.scalar(
                select(func.count(ProviderCall.id)).where(
                    ProviderCall.purpose.in_(
                        ("cover_image_generate", "default_workflow_image_generate")
                    )
                )
            )
            == 0
        )
