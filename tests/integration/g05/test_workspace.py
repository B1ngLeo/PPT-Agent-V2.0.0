from __future__ import annotations

import hashlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from instant_ppt_api.planning import DeterministicPlanningGateway
from instant_ppt_domain.models import PlanningJob
from instant_ppt_domain.planning_jobs import (
    finish_planning_success,
    start_planning_attempt,
)
from instant_ppt_domain.workspace import (
    get_intent_revision,
    get_outline_revision,
    serialize_intent_revision,
    serialize_outline_revision,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

ALICE = {"X-Dev-User-Subject": "g05-alice", "X-Dev-User-Name": "Alice"}
BOB = {"X-Dev-User-Subject": "g05-bob", "X-Dev-User-Name": "Bob"}


def _mutation(data: dict[str, Any], base: str | None = None) -> dict[str, Any]:
    return {"schemaVersion": 1, "data": data, "baseRevisionId": base}


def _create_key(topic: str) -> str:
    return f"create-{hashlib.sha256(topic.encode('utf-8')).hexdigest()[:20]}"


def _create(client: TestClient, *, topic: str = "2027 年产品增长策略") -> dict[str, Any]:
    response = client.post(
        "/v1/drafts",
        headers={**ALICE, "Idempotency-Key": _create_key(topic)},
        json=_mutation({"topic": topic, "mode": "native"}),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _complete_planning_job(client: TestClient, job_id: str) -> dict[str, Any]:
    factory = client.app.state.session_factory
    gateway = DeterministicPlanningGateway()
    with factory.begin() as session:
        queued = session.get(PlanningJob, job_id)
        assert queued is not None
        job = start_planning_attempt(session, job_id, queued.organization_id)
        payload = dict(job.request_payload)
        operation = job.operation
        organization_id = job.organization_id
        if operation == "outline_generate":
            intent = serialize_intent_revision(
                get_intent_revision(session, payload["intentRevisionId"], organization_id)
            )
            existing_id = payload.get("existingOutlineRevisionId")
            existing = (
                serialize_outline_revision(
                    session,
                    get_outline_revision(session, existing_id, organization_id),
                )
                if existing_id
                else None
            )
    if operation == "intent_infer":
        result = gateway.infer_intent(
            topic=payload["topic"],
            source_refs=payload["sourceRefs"],
            language=payload["language"],
        )
    else:
        result = gateway.generate_outline(
            intent=intent,
            existing=existing,
            instruction=payload["instruction"],
            action=payload["action"],
            target_slide_id=payload["targetSlideId"],
        )
    with factory.begin() as session:
        finish_planning_success(
            session,
            job_id,
            organization_id,
            result=result.data,
            provider=result.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            repair_count=result.repair_count,
        )
    response = client.get(f"/v1/planning-jobs/{job_id}", headers=ALICE)
    assert response.status_code == 200, response.text
    return response.json()["data"]["result"]


def _infer(client: TestClient, draft_id: str, base: str | None = None) -> dict[str, Any]:
    response = client.post(
        f"/v1/drafts/{draft_id}/intent:infer",
        headers={**ALICE, "Idempotency-Key": f"intent-{draft_id}-{base}"},
        json=_mutation({"language": "zh-CN"}, base),
    )
    assert response.status_code == 202, response.text
    job = response.json()["data"]
    assert response.headers["Location"] == f"/v1/planning-jobs/{job['planningJobId']}"
    return _complete_planning_job(client, job["planningJobId"])


def _generate(
    client: TestClient,
    draft_id: str,
    base: str | None = None,
    *,
    action: str = "generate",
    instruction: str = "",
) -> dict[str, Any]:
    response = client.post(
        f"/v1/drafts/{draft_id}/outline:generate",
        headers={
            **ALICE,
            "Idempotency-Key": f"outline-{draft_id}-{base}-{action}-{instruction}",
        },
        json=_mutation({"action": action, "instruction": instruction}, base),
    )
    assert response.status_code == 202, response.text
    job = response.json()["data"]
    assert response.headers["Location"] == f"/v1/planning-jobs/{job['planningJobId']}"
    return _complete_planning_job(client, job["planningJobId"])


def _manual_outline(
    client: TestClient,
    draft_id: str,
    base: str,
    outline: dict[str, Any],
    *,
    operation: str,
    suffix: str,
) -> Any:
    return client.post(
        f"/v1/drafts/{draft_id}/outline-revisions",
        headers={**ALICE, "Idempotency-Key": f"manual-{base}-{operation}-{suffix}"},
        json=_mutation(
            {
                "storySummary": outline["storySummary"],
                "targetSlideCount": outline["targetSlideCount"],
                "slides": outline["slides"],
                "operation": operation,
            },
            base,
        ),
    )


def test_topic_intent_outline_refresh_approval_and_post_approval_revision(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    templates = client.get("/v1/templates", headers=ALICE)
    assert templates.status_code == 200
    template_items = templates.json()["data"]["items"]
    assert len(template_items) == 3
    assert {item["mode"] for item in template_items} == {"native"}

    entitlement = client.get("/v1/me/entitlements", headers=ALICE)
    assert entitlement.status_code == 200
    assert entitlement.json()["data"]["allowedModes"] == ["native"]

    draft = _create(client)
    replay = client.post(
        "/v1/drafts",
        headers={**ALICE, "Idempotency-Key": _create_key("2027 年产品增长策略")},
        json=_mutation({"topic": "2027 年产品增长策略", "mode": "native"}),
    )
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["resourceId"] == draft["draftId"]

    empty = client.post(
        "/v1/drafts",
        headers={**ALICE, "Idempotency-Key": "empty"},
        json=_mutation({"topic": "", "mode": "native"}),
    )
    assert empty.status_code == 422

    intent = _infer(client, draft["draftId"])
    assert intent["language"] == "zh-CN"
    assert intent["actor"]["kind"] == "ai"
    assert intent["providerCallId"]

    generated = _generate(client, draft["draftId"])
    assert len(generated["slides"]) == generated["targetSlideCount"] == 8
    generated_ids = [slide["outlineSlideId"] for slide in generated["slides"]]
    moved = {
        **generated,
        "slides": [generated["slides"][1], generated["slides"][0], *generated["slides"][2:]],
    }
    moved_response = _manual_outline(
        client,
        draft["draftId"],
        generated["outlineRevisionId"],
        moved,
        operation="move",
        suffix="one",
    )
    assert moved_response.status_code == 201, moved_response.text
    moved_data = moved_response.json()["data"]
    assert {slide["outlineSlideId"] for slide in moved_data["slides"]} == set(generated_ids)
    assert moved_data["slides"][0]["outlineSlideId"] == generated_ids[1]

    old = client.get(f"/v1/outline-revisions/{generated['outlineRevisionId']}", headers=ALICE)
    assert old.json()["data"]["slides"][0]["outlineSlideId"] == generated_ids[0]

    approval = client.post(
        f"/v1/outline-revisions/{moved_data['outlineRevisionId']}:approve",
        headers={**ALICE, "Idempotency-Key": "approve-moved"},
        json=_mutation({}),
    )
    assert approval.status_code == 200, approval.text
    summary = approval.json()["data"]
    assert summary["intentRevisionId"] == intent["intentRevisionId"]
    assert summary["outlineRevisionId"] == moved_data["outlineRevisionId"]
    assert summary["templateVersionId"] == draft["templateVersionId"]
    assert summary["mode"] == "native"
    assert summary["boundary"] == "generation_not_started"

    edited = {**moved_data, "slides": [dict(slide) for slide in moved_data["slides"]]}
    edited["slides"][0] = {**edited["slides"][0], "title": "批准后的新探索"}
    post_approval = _manual_outline(
        client,
        draft["draftId"],
        moved_data["outlineRevisionId"],
        edited,
        operation="edit",
        suffix="after-approval",
    )
    assert post_approval.status_code == 201
    restored = client.get(f"/v1/drafts/{draft['draftId']}", headers=ALICE).json()["data"]
    assert restored["currentOutlineRevisionId"] != restored["approvedOutlineRevisionId"]
    assert restored["generationSummary"]["snapshotInputHash"] == summary["snapshotInputHash"]
    assert restored["planningProvider"] == {
        "provider": "fake",
        "model": "deterministic-fake-v1",
        "purpose": "outline_generate",
    }

    with session_factory() as session:
        provider_rows = session.execute(
            text(
                "SELECT provider, model, request_hash, repair_count FROM provider_calls "
                "ORDER BY created_at"
            )
        ).all()
        assert provider_rows == [
            ("fake", "deterministic-fake-v1", provider_rows[0].request_hash, 0),
            ("fake", "deterministic-fake-v1", provider_rows[1].request_hash, 0),
        ]
        assert all(len(row.request_hash) == 64 for row in provider_rows)
        planning_usage = session.execute(
            text(
                "SELECT count(*), sum(quantity) FROM usage_ledger "
                "WHERE metric = 'model_tokens' AND job_id IS NULL"
            )
        ).one()
        assert planning_usage[0] == 2
        assert planning_usage[1] > 0
        assert (
            session.execute(
                text("SELECT count(*) FROM provider_calls WHERE provider LIKE '%image%'")
            ).scalar_one()
            == 0
        )


def test_concurrent_base_conflict_and_undo_redo_create_new_revisions(client: TestClient) -> None:
    draft = _create(client, topic="并发与撤销测试")
    _infer(client, draft["draftId"])
    original = _generate(client, draft["draftId"])
    base = original["outlineRevisionId"]

    first_edit = {**original, "slides": [dict(slide) for slide in original["slides"]]}
    first_edit["slides"][0] = {**first_edit["slides"][0], "title": "合法并发提交"}
    accepted = _manual_outline(
        client, draft["draftId"], base, first_edit, operation="edit", suffix="accepted"
    )
    assert accepted.status_code == 201
    accepted_data = accepted.json()["data"]

    stale_edit = {**original, "slides": [dict(slide) for slide in original["slides"]]}
    stale_edit["slides"][0] = {**stale_edit["slides"][0], "title": "不应覆盖"}
    rejected = _manual_outline(
        client, draft["draftId"], base, stale_edit, operation="edit", suffix="stale"
    )
    assert rejected.status_code == 412
    assert rejected.json()["code"] == "revision_conflict"

    undo = _manual_outline(
        client,
        draft["draftId"],
        accepted_data["outlineRevisionId"],
        original,
        operation="undo",
        suffix="undo",
    )
    assert undo.status_code == 201
    undo_data = undo.json()["data"]
    assert undo_data["outlineRevisionId"] not in {base, accepted_data["outlineRevisionId"]}
    assert undo_data["slides"] == original["slides"]

    redo = _manual_outline(
        client,
        draft["draftId"],
        undo_data["outlineRevisionId"],
        accepted_data,
        operation="redo",
        suffix="redo",
    )
    assert redo.status_code == 201
    assert redo.json()["data"]["slides"] == accepted_data["slides"]
    revisions = client.get(
        f"/v1/drafts/{draft['draftId']}/outline-revisions", headers=ALICE
    ).json()["data"]["items"]
    assert len(revisions) == 4


def test_autosave_etag_history_delete_and_cross_tenant(client: TestClient) -> None:
    draft = _create(client, topic="自动保存恢复")
    loaded = client.get(f"/v1/drafts/{draft['draftId']}", headers=ALICE)
    assert loaded.status_code == 200
    etag = loaded.headers["ETag"]

    saved = client.patch(
        f"/v1/drafts/{draft['draftId']}",
        headers={**ALICE, "If-Match": etag},
        json=_mutation({"topic": "自动保存后的主题"}),
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["topic"] == "自动保存后的主题"
    assert saved.headers["ETag"] != etag

    stale = client.patch(
        f"/v1/drafts/{draft['draftId']}",
        headers={**ALICE, "If-Match": etag},
        json=_mutation({"topic": "会丢数据的旧提交"}),
    )
    assert stale.status_code == 412
    assert (
        client.get(f"/v1/drafts/{draft['draftId']}", headers=ALICE).json()["data"]["topic"]
        == "自动保存后的主题"
    )

    assert client.get(f"/v1/drafts/{draft['draftId']}", headers=BOB).status_code == 404
    assert client.get("/v1/history", headers=BOB).json()["data"]["items"] == []
    history = client.get("/v1/history?limit=1", headers=ALICE).json()["data"]["items"]
    assert history[0]["draftId"] == draft["draftId"]

    deleted = client.delete(f"/v1/drafts/{draft['draftId']}", headers=ALICE)
    assert deleted.status_code == 204
    assert client.get(f"/v1/drafts/{draft['draftId']}", headers=ALICE).status_code == 404


def test_database_rejects_mutating_immutable_versions(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    draft = _create(client, topic="不可变版本")
    intent = _infer(client, draft["draftId"])
    outline = _generate(client, draft["draftId"])

    for statement in (
        "UPDATE template_versions SET mode='visual' WHERE id=:id",
        "UPDATE intent_revisions SET payload='{}'::jsonb WHERE id=:id",
        "DELETE FROM outline_revisions WHERE id=:id",
    ):
        with session_factory() as session, pytest.raises(DBAPIError, match="immutable"):
            identifier = (
                draft["templateVersionId"]
                if "template_versions" in statement
                else (
                    intent["intentRevisionId"]
                    if "intent_revisions" in statement
                    else outline["outlineRevisionId"]
                )
            )
            session.execute(text(statement), {"id": identifier})
            session.commit()
