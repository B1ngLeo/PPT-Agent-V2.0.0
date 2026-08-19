from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

from fastapi.testclient import TestClient
from instant_ppt_domain.effective_spec import persist_initial_effective_revision
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    DesignSpecEditPatch,
    EffectiveDesignSpecRevision,
    ExportJob,
    GenerationArtifact,
    GenerationSnapshot,
    PresentationRevision,
    ProjectCleanupJob,
    SlideVersion,
    WorkflowRun,
)
from instant_ppt_worker.generation_pipeline import process_generation_job
from instant_ppt_worker.presentation_pipeline import (
    process_export,
    process_project_cleanup,
    process_slide_regeneration,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

ALICE = {"X-Dev-User-Subject": "g07-alice", "X-Dev-User-Name": "Alice"}
BOB = {"X-Dev-User-Subject": "g07-bob", "X-Dev-User-Name": "Bob"}


def _mutation(data: dict[str, Any], base: str | None = None) -> dict[str, Any]:
    return {"schemaVersion": 1, "data": data, "baseRevisionId": base}


def _published_presentation(
    client: TestClient,
    session_factory: sessionmaker[Session],
    store: Any,
    *,
    failure_modes: dict[int, str] | None = None,
) -> dict[str, Any]:
    draft_response = client.post(
        "/v1/drafts",
        headers={**ALICE, "Idempotency-Key": f"draft-{new_ulid()}"},
        json=_mutation({"topic": "G07 编辑导出验证", "mode": "native"}),
    )
    assert draft_response.status_code == 201, draft_response.text
    draft = draft_response.json()["data"]
    intent = client.post(
        f"/v1/drafts/{draft['draftId']}/intent:infer",
        headers={**ALICE, "Idempotency-Key": f"intent-{new_ulid()}"},
        json=_mutation({"language": "zh-CN"}),
    )
    assert intent.status_code == 201, intent.text
    slides = [
        {
            "outlineSlideId": new_ulid(),
            "type": "cover" if position == 1 else "content",
            "title": f"稳定页面 {position}",
            "keyPoints": [f"结论 {position}", f"行动 {position}"],
            "sourceCitations": [],
        }
        for position in range(1, 4)
    ]
    outline_response = client.post(
        f"/v1/drafts/{draft['draftId']}/outline-revisions",
        headers={**ALICE, "Idempotency-Key": f"outline-{new_ulid()}"},
        json=_mutation(
            {
                "storySummary": "编辑、重生成和精确版本导出",
                "targetSlideCount": 4,
                "slides": slides,
                "operation": "edit",
            }
        ),
    )
    assert outline_response.status_code == 201, outline_response.text
    outline = outline_response.json()["data"]
    approval = client.post(
        f"/v1/outline-revisions/{outline['outlineRevisionId']}:approve",
        headers={**ALICE, "Idempotency-Key": f"approve-{new_ulid()}"},
        json=_mutation({}),
    )
    assert approval.status_code == 200, approval.text
    generation = client.post(
        f"/v1/drafts/{draft['draftId']}/generation-jobs",
        headers={**ALICE, "Idempotency-Key": f"generation-{new_ulid()}"},
        json=_mutation(
            {"failureModes": failure_modes or {}, "continueLimitedDraft": True}
        ),
    )
    assert generation.status_code == 202, generation.text
    job = generation.json()["data"]
    result = process_generation_job(
        session_factory,
        job["jobId"],
        f"g07-generation-{new_ulid()}",
        organization_id=job["organizationId"],
        object_store=store,
    )
    assert result in {"succeeded", "partially_succeeded"}
    generated = client.get(f"/v1/jobs/{job['jobId']}", headers=ALICE).json()["data"]
    return {
        "draft": draft,
        "job": job,
        "presentation": client.get(
            f"/v1/presentations/{generated['presentation']['presentationId']}",
            headers=ALICE,
        ).json()["data"],
    }


def _revision(
    client: TestClient,
    presentation: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    key: str,
) -> dict[str, Any]:
    approved_operations = [
        {
            **operation,
            **(
                {"rosterApprovalReceiptSha256": "a" * 64}
                if operation.get("type") in {"move", "delete"}
                else {}
            ),
        }
        for operation in operations
    ]
    response = client.post(
        f"/v1/presentations/{presentation['presentationId']}/revisions",
        headers={**ALICE, "Idempotency-Key": key},
        json=_mutation(
            {"operations": approved_operations}, presentation["currentRevisionId"]
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _attach_default_effective_revision(
    session_factory: sessionmaker[Session], presentation: dict[str, Any]
) -> tuple[str, str]:
    revision_id = presentation["currentRevisionId"]
    with session_factory.begin() as session:
        revision = session.get(PresentationRevision, revision_id)
        snapshot = session.get(GenerationSnapshot, revision.snapshot_id)
        baseline_link = session.scalar(
            select(GenerationArtifact).where(
                GenerationArtifact.job_id == revision.generation_job_id,
                GenerationArtifact.kind == "generation_baseline_pptx",
            )
        )
        baseline = session.get(Artifact, baseline_link.artifact_id)
        existing = session.scalar(
            select(EffectiveDesignSpecRevision).where(
                EffectiveDesignSpecRevision.presentation_revision_id == revision.id
            )
        )
        if existing is not None:
            return existing.id, baseline.id
        run = WorkflowRun(
            id=new_ulid(),
            organization_id=revision.organization_id,
            generation_job_id=revision.generation_job_id,
            snapshot_id=revision.snapshot_id,
            route="generate_pptx",
            profile="default-agentic",
            workflow_version="instant-ppt-default@v2.0.0",
            engine_version="ppt-master@v4.7.0",
            request_sha256="d" * 64,
            approved_snapshot_sha256=snapshot.snapshot_sha256,
            status="succeeded",
            stage="publish",
            attempt=1,
            max_attempts=5,
            runtime_policy={"test": True},
            usage={},
            error={},
        )
        session.add(run)
        session.flush()
        roster = [
            {
                "slideId": slide["slideId"],
                "outlineSlideId": slide["outlineSlideId"],
                "pnn": f"P{index:02d}",
                "role": "cover" if index == 1 else "content",
                "title": slide["title"],
                "body": slide["body"],
                "artifactId": slide["artifactId"],
            }
            for index, slide in enumerate(presentation["currentRevision"]["slides"], start=1)
        ]
        effective = persist_initial_effective_revision(
            session,
            organization_id=revision.organization_id,
            workflow_run_id=run.id,
            presentation_revision_id=revision.id,
            design_spec_sha256="a" * 64,
            spec_lock_sha256="b" * 64,
            source_manifest_sha256=snapshot.snapshot_sha256,
            roster=roster,
            canonical_artifacts={
                "pptxArtifactId": baseline.id,
                "pptxSha256": baseline.sha256,
                "finalSvgReportSha256": "e" * 64,
                "packageQaSha256": "f" * 64,
            },
        )
        return effective.id, baseline.id


def test_operation_set_is_immutable_optimistic_and_retains_stable_slide_ids(
    client: TestClient,
    session_factory: sessionmaker[Session],
    object_store: Any,
) -> None:
    created = _published_presentation(client, session_factory, object_store)
    presentation = created["presentation"]
    slides = presentation["currentRevision"]["slides"]
    stable_ids = [slide["slideId"] for slide in slides]
    updated = _revision(
        client,
        presentation,
        [
            {
                "type": "update_text",
                "slideId": stable_ids[0],
                "title": "用户已编辑标题",
                "body": ["保留事实", "强化行动"],
            },
            {"type": "move", "slideId": stable_ids[2], "position": 1},
        ],
        key="edit-and-move",
    )
    assert [slide["slideId"] for slide in updated["slides"]] == [
        stable_ids[2],
        stable_ids[0],
        stable_ids[1],
    ]
    assert next(x for x in updated["slides"] if x["slideId"] == stable_ids[0])["title"] == (
        "用户已编辑标题"
    )
    stale = client.post(
        f"/v1/presentations/{presentation['presentationId']}/revisions",
        headers={**ALICE, "Idempotency-Key": "stale-revision"},
        json=_mutation(
            {"operations": [{"type": "delete", "slideId": stable_ids[1]}]},
            presentation["currentRevisionId"],
        ),
    )
    assert stale.status_code == 412
    foreign = client.get(f"/v1/presentations/{presentation['presentationId']}", headers=BOB)
    assert foreign.status_code == 404
    current = client.get(
        f"/v1/presentations/{presentation['presentationId']}", headers=ALICE
    ).json()["data"]
    while len(current["currentRevision"]["slides"]) > 1:
        current_revision = _revision(
            client,
            current,
            [
                {
                    "type": "delete",
                    "slideId": current["currentRevision"]["slides"][-1]["slideId"],
                }
            ],
            key=f"delete-{len(current['currentRevision']['slides'])}",
        )
        current = client.get(
            f"/v1/presentations/{presentation['presentationId']}", headers=ALICE
        ).json()["data"]
        assert current_revision["slides"]
    rejected = client.post(
        f"/v1/presentations/{presentation['presentationId']}/revisions",
        headers={**ALICE, "Idempotency-Key": "delete-last"},
        json=_mutation(
            {
                "operations": [
                    {
                        "type": "delete",
                        "slideId": current["currentRevision"]["slides"][0]["slideId"],
                    }
                ]
            },
            current["currentRevisionId"],
        ),
    )
    assert rejected.status_code == 422
    with session_factory() as session:
        assert session.scalar(select(func.count(PresentationRevision.id))) >= 4
        assert session.scalar(select(func.count(Artifact.id))) >= 10


def test_regeneration_keeps_old_ready_version_until_qa_then_switches_atomically(
    client: TestClient,
    session_factory: sessionmaker[Session],
    object_store: Any,
) -> None:
    created = _published_presentation(client, session_factory, object_store)
    presentation = created["presentation"]
    old_revision_id = presentation["currentRevisionId"]
    target = presentation["currentRevision"]["slides"][1]
    queued = client.post(
        f"/v1/presentations/{presentation['presentationId']}/slides/{target['slideId']}:regenerate",
        headers={**ALICE, "Idempotency-Key": "regenerate-one"},
        json=_mutation({"instruction": "把行动写得更明确"}, presentation["currentRevisionId"]),
    )
    assert queued.status_code == 202, queued.text
    operation = queued.json()["data"]
    before = client.get(
        f"/v1/presentations/{presentation['presentationId']}", headers=ALICE
    ).json()["data"]
    assert before["currentRevisionId"] == old_revision_id
    assert (
        next(
            slide
            for slide in before["currentRevision"]["slides"]
            if slide["slideId"] == target["slideId"]
        )["artifactId"]
        == target["artifactId"]
    )
    assert (
        process_slide_regeneration(
            session_factory,
            operation["regenerationJobId"],
            created["job"]["organizationId"],
            object_store=object_store,
        )
        == "succeeded"
    )
    after = client.get(f"/v1/presentations/{presentation['presentationId']}", headers=ALICE).json()[
        "data"
    ]
    changed = next(
        slide
        for slide in after["currentRevision"]["slides"]
        if slide["slideId"] == target["slideId"]
    )
    assert after["currentRevisionId"] != old_revision_id
    assert changed["slideId"] == target["slideId"]
    assert changed["artifactId"] != target["artifactId"]
    assert changed["sourceSlideVersionId"] == target["slideVersionId"]
    status = client.get(f"/v1/operations/{operation['regenerationJobId']}", headers=ALICE).json()[
        "data"
    ]
    assert status["status"] == "succeeded"


def test_export_binds_exact_revision_while_concurrent_edit_advances_current(
    client: TestClient,
    session_factory: sessionmaker[Session],
    object_store: Any,
) -> None:
    created = _published_presentation(client, session_factory, object_store)
    presentation = created["presentation"]
    export_revision_id = presentation["currentRevisionId"]
    queued = client.post(
        f"/v1/presentations/{presentation['presentationId']}/exports",
        headers={**ALICE, "Idempotency-Key": "exact-export"},
        json=_mutation({"presentationRevisionId": export_revision_id}, export_revision_id),
    )
    assert queued.status_code == 202, queued.text
    export = queued.json()["data"]
    first_slide = presentation["currentRevision"]["slides"][0]
    concurrent = _revision(
        client,
        presentation,
        [
            {
                "type": "update_text",
                "slideId": first_slide["slideId"],
                "title": "并发编辑后的标题",
            }
        ],
        key="concurrent-edit",
    )
    assert concurrent["presentationRevisionId"] != export_revision_id
    assert (
        process_export(
            session_factory,
            export["exportId"],
            created["job"]["organizationId"],
            object_store=object_store,
        )
        == "succeeded"
    )
    completed = client.get(f"/v1/exports/{export['exportId']}", headers=ALICE).json()["data"]
    assert completed["presentationRevisionId"] == export_revision_id
    with session_factory() as session:
        row = session.get(ExportJob, export["exportId"])
        manifest_artifact = session.get(Artifact, row.manifest_artifact_id)
        pptx_artifact = session.get(Artifact, row.artifact_id)
        manifest = json.loads(object_store.objects[manifest_artifact.object_key])
        assert manifest["presentationRevisionId"] == export_revision_id
        # An untouched Default revision must bind the canonical generated PPTX
        # instead of rebuilding the legacy DeckPlan during exact export.
        assert manifest["artifact"]["artifactType"] == "generation_baseline_pptx"
        assert manifest["renderSkipped"] is True
        assert pptx_artifact.artifact_type == "generation_baseline_pptx"
        with zipfile.ZipFile(BytesIO(object_store.objects[pptx_artifact.object_key])) as package:
            assert "ppt/presentation.xml" in package.namelist()
    authorization = client.post(
        f"/v1/artifacts/{completed['artifactId']}:authorize-download",
        headers={**ALICE, "Idempotency-Key": "export-download"},
        json=_mutation({}),
    )
    assert authorization.status_code == 200
    assert authorization.json()["data"]["downloadUrl"].startswith("https://objects.local/")
    assert (
        client.post(
            f"/v1/artifacts/{completed['artifactId']}:authorize-download",
            headers={**BOB, "Idempotency-Key": "foreign-download"},
            json=_mutation({}),
        ).status_code
        == 404
    )


def test_default_effective_revision_drives_edit_regenerate_and_exact_export(
    client: TestClient,
    session_factory: sessionmaker[Session],
    object_store: Any,
) -> None:
    created = _published_presentation(client, session_factory, object_store)
    presentation = created["presentation"]
    initial_effective_id, baseline_pptx_id = _attach_default_effective_revision(
        session_factory, presentation
    )

    initial_export_response = client.post(
        f"/v1/presentations/{presentation['presentationId']}/exports",
        headers={**ALICE, "Idempotency-Key": "default-initial-exact-export"},
        json=_mutation(
            {"presentationRevisionId": presentation["currentRevisionId"]},
            presentation["currentRevisionId"],
        ),
    )
    assert initial_export_response.status_code == 202, initial_export_response.text
    initial_export = initial_export_response.json()["data"]
    assert (
        process_export(
            session_factory,
            initial_export["exportId"],
            created["job"]["organizationId"],
            object_store=object_store,
        )
        == "succeeded"
    )
    with session_factory() as session:
        export_row = session.get(ExportJob, initial_export["exportId"])
        export_manifest = session.get(Artifact, export_row.manifest_artifact_id)
        manifest = json.loads(object_store.objects[export_manifest.object_key])
        assert export_row.artifact_id == baseline_pptx_id
        assert manifest["renderSkipped"] is True
        assert manifest["effectiveSpecRevisionId"] == initial_effective_id

    target = presentation["currentRevision"]["slides"][1]
    edited = _revision(
        client,
        presentation,
        [
            {
                "type": "update_text",
                "slideId": target["slideId"],
                "title": "用户有效版本中的新标题",
                "body": ["用户有效版本中的新正文"],
            }
        ],
        key="default-effective-edit",
    )
    edited_target = next(
        slide for slide in edited["slides"] if slide["slideId"] == target["slideId"]
    )
    assert edited_target["artifactId"] is None
    assert edited["effectiveSpecRevisionId"] != initial_effective_id
    assert edited["wholeDeckFinalGate"] == "stale"
    with session_factory() as session:
        effective = session.get(EffectiveDesignSpecRevision, edited["effectiveSpecRevisionId"])
        patches = list(
            session.scalars(
                select(DesignSpecEditPatch)
                .where(DesignSpecEditPatch.effective_spec_revision_id == effective.id)
                .order_by(DesignSpecEditPatch.sequence)
            )
        )
        assert [patch.object_key for patch in patches] == [
            "§IX/P02/title",
            "§IX/P02/body",
        ]
        assert effective.payload["roster"][1]["title"] == "用户有效版本中的新标题"

    current = client.get(
        f"/v1/presentations/{presentation['presentationId']}", headers=ALICE
    ).json()["data"]
    instruction = "把结论改得更有行动性，但不要把这句话放进正文"
    queued = client.post(
        f"/v1/presentations/{presentation['presentationId']}/slides/{target['slideId']}:regenerate",
        headers={**ALICE, "Idempotency-Key": "default-effective-regenerate"},
        json=_mutation({"instruction": instruction}, current["currentRevisionId"]),
    )
    assert queued.status_code == 202, queued.text
    operation = queued.json()["data"]
    assert (
        process_slide_regeneration(
            session_factory,
            operation["regenerationJobId"],
            created["job"]["organizationId"],
            object_store=object_store,
        )
        == "succeeded"
    )
    regenerated = client.get(
        f"/v1/presentations/{presentation['presentationId']}", headers=ALICE
    ).json()["data"]["currentRevision"]
    assert regenerated["effectiveSpecRevisionId"] != edited["effectiveSpecRevisionId"]
    assert regenerated["wholeDeckFinalGate"] == "passed"
    assert instruction not in json.dumps(regenerated, ensure_ascii=False)
    assert (
        next(slide for slide in regenerated["slides"] if slide["slideId"] == target["slideId"])[
            "slideId"
        ]
        == target["slideId"]
    )
    with session_factory() as session:
        regenerated_row = session.get(
            PresentationRevision, regenerated["presentationRevisionId"]
        )
        regenerated_manifest = session.get(Artifact, regenerated_row.manifest_artifact_id)
        manifest = json.loads(object_store.objects[regenerated_manifest.object_key])
        assert manifest["engineProfile"] == "default-agentic-revision"
        assert manifest["quickGenerate"] is False
        assert manifest["contentMode"] == "limited-general-draft"
        assert manifest["wholeDeckFinalQa"]["passed"] is True
        assert manifest["wholeDeckFinalQa"]["quickGenerate"] is False
        assert manifest["evidenceMapSha256"]
        assert manifest["contentQaSha256"]

    final_export_response = client.post(
        f"/v1/presentations/{presentation['presentationId']}/exports",
        headers={**ALICE, "Idempotency-Key": "default-effective-final-export"},
        json=_mutation(
            {"presentationRevisionId": regenerated["presentationRevisionId"]},
            regenerated["presentationRevisionId"],
        ),
    )
    assert final_export_response.status_code == 202, final_export_response.text
    final_export = final_export_response.json()["data"]
    assert (
        process_export(
            session_factory,
            final_export["exportId"],
            created["job"]["organizationId"],
            object_store=object_store,
        )
        == "succeeded"
    )
    with session_factory() as session:
        export_row = session.get(ExportJob, final_export["exportId"])
        export_manifest = session.get(Artifact, export_row.manifest_artifact_id)
        manifest = json.loads(object_store.objects[export_manifest.object_key])
        assert "renderSkipped" not in manifest
        assert manifest["effectiveSpecSha256"] == regenerated["effectiveSpecSha256"]
        assert manifest["wholeDeckFinalQaSha256"]
        assert manifest["engineProfile"] == "default-agentic-revision"
        assert manifest["quickGenerate"] is False
        assert manifest["contentMode"] == "limited-general-draft"
        assert manifest["evidenceMapSha256"]
        assert manifest["contentQaSha256"]
        assert manifest["exactRoster"] == [
            f"P{index:02d}" for index in range(1, len(regenerated["slides"]) + 1)
        ]


def test_partial_requires_decision_and_delete_revokes_all_routes_and_objects(
    client: TestClient,
    session_factory: sessionmaker[Session],
    object_store: Any,
) -> None:
    created = _published_presentation(
        client, session_factory, object_store, failure_modes={3: "always"}
    )
    presentation = created["presentation"]
    assert presentation["currentRevision"]["partial"] is True
    rejected_export = client.post(
        f"/v1/presentations/{presentation['presentationId']}/exports",
        headers={**ALICE, "Idempotency-Key": "partial-export-rejected"},
        json=_mutation(
            {"presentationRevisionId": presentation["currentRevisionId"]},
            presentation["currentRevisionId"],
        ),
    )
    assert rejected_export.status_code == 422
    accepted = _revision(
        client,
        presentation,
        [{"type": "accept_missing"}],
        key="accept-missing",
    )
    assert accepted["partial"] is True and accepted["acceptedMissing"] is True
    current = client.get(
        f"/v1/presentations/{presentation['presentationId']}", headers=ALICE
    ).json()["data"]
    export_response = client.post(
        f"/v1/presentations/{presentation['presentationId']}/exports",
        headers={**ALICE, "Idempotency-Key": "partial-export-accepted"},
        json=_mutation(
            {"presentationRevisionId": current["currentRevisionId"]},
            current["currentRevisionId"],
        ),
    )
    assert export_response.status_code == 202
    data_export = client.post(
        f"/v1/drafts/{created['draft']['draftId']}:export-data",
        headers={**ALICE, "Idempotency-Key": "project-data"},
        json=_mutation({}),
    )
    assert data_export.status_code == 202, data_export.text
    assert data_export.json()["data"]["snapshotSha256"]
    history = client.get("/v1/history", headers=ALICE).json()["data"]["items"]
    assert history[0]["historyState"] == "result"
    assert history[0]["presentationId"] == presentation["presentationId"]
    assert "presentation=" in history[0]["route"]
    object_count = len(object_store.objects)
    deleted = client.delete(f"/v1/drafts/{created['draft']['draftId']}", headers=ALICE)
    assert deleted.status_code == 204
    assert client.get(f"/v1/jobs/{created['job']['jobId']}", headers=ALICE).status_code == 404
    assert (
        client.get(f"/v1/jobs/{created['job']['jobId']}/events", headers=ALICE).status_code == 404
    )
    assert (
        client.get(f"/v1/presentations/{presentation['presentationId']}", headers=ALICE).status_code
        == 404
    )
    with session_factory() as session:
        cleanup = session.scalar(
            select(ProjectCleanupJob).where(
                ProjectCleanupJob.draft_id == created["draft"]["draftId"]
            )
        )
        assert cleanup is not None and cleanup.status == "queued"
        cleanup_id = cleanup.id
    assert (
        process_project_cleanup(
            session_factory,
            cleanup_id,
            created["job"]["organizationId"],
            object_store=object_store,
        )
        == "succeeded"
    )
    assert len(object_store.objects) < object_count
    with session_factory() as session:
        cleanup = session.get(ProjectCleanupJob, cleanup_id)
        assert cleanup.status == "succeeded"
        assert cleanup.result["removedObjectCount"] > 0
        assert (
            session.scalar(select(func.count(Artifact.id)).where(Artifact.status == "published"))
            == 0
        )
        assert session.scalar(select(func.count(SlideVersion.id))) >= 3
