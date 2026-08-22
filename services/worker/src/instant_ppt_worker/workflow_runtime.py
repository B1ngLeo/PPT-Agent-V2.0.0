"""Persistence bridge from workflow project receipts/checkpoints to runtime rows."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    GenerationJob,
    GenerationSnapshot,
    WorkflowAgentToolCall,
    WorkflowAgentTurn,
    WorkflowCheckpointSet,
    WorkflowGateReceipt,
    WorkflowIntermediateArtifact,
    WorkflowRun,
    WorkflowStageAttempt,
)
from instant_ppt_domain.service import canonical_sha256
from sqlalchemy import select
from sqlalchemy.orm import Session

from instant_ppt_worker.workflow_models import WorkflowRequestV2, WorkflowResultV2

_RECEIPT_STAGES = {
    "attribution": "attribution_guard",
    "stage1-confirmation": "stage1",
    "template-handoff": "template_handoff",
    "stage2-confirmation": "stage2",
    "image-resources": "design_spec_gate1",
    "page-blueprint-gate": "design_spec_gate1",
    "design-spec-gate1": "design_spec_gate1",
    "refine-spec-approval": "refine_spec",
    "spec-lock-gate2": "spec_lock_gate2",
    "design-parameter-confirmation": "design_parameters",
    "live-preview": "live_preview",
    "first-page-gate": "first_page_gate",
    "final-svg-gate": "final_svg_gate",
    "chart-gate": "chart_gate",
    "content-gate": "design_spec_gate1",
    "final-svg-content-gate": "final_svg_content_gate",
    "speaker-notes": "notes",
    "custom-animations": "animations",
    "step7-finalize": "step7_finalize",
    "step7-export": "step7_export",
    "pptx-content-gate": "pptx_content_gate",
    "postflight": "postflight",
    "narration-audio": "narration",
    "publication": "publish",
}


def begin_workflow_run(
    session: Session,
    *,
    job: GenerationJob,
    snapshot: GenerationSnapshot,
    request: WorkflowRequestV2,
    request_sha256: str,
    worker_id: str,
    lease_seconds: int,
) -> WorkflowRun:
    row = session.scalar(
        select(WorkflowRun).where(WorkflowRun.generation_job_id == job.id).with_for_update()
    )
    now = datetime.now(UTC)
    fencing_token = new_ulid()
    if row is None:
        row = WorkflowRun(
            id=request.workflow_run_id,
            organization_id=job.organization_id,
            generation_job_id=job.id,
            snapshot_id=snapshot.id,
            route=request.route,
            profile=request.profile,
            workflow_version=request.versions.workflow,
            engine_version=request.versions.engine,
            request_sha256=request_sha256,
            approved_snapshot_sha256=snapshot.snapshot_sha256,
            status="running",
            stage="attribution_guard",
            attempt=1,
            max_attempts=request.runtime.max_stage_attempts,
            fencing_token=fencing_token,
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            heartbeat_at=now,
            runtime_policy=request.runtime.model_dump(by_alias=True, mode="json"),
            usage={},
            error={},
        )
        session.add(row)
    else:
        if row.request_sha256 != request_sha256:
            raise RuntimeError("workflow request changed across a recovery attempt")
        if row.attempt >= row.max_attempts:
            raise RuntimeError("workflow recovery attempt limit is exhausted")
        row.attempt += 1
        row.status = "running"
        row.stage = "attribution_guard"
        row.fencing_token = fencing_token
        row.lease_owner = worker_id
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.heartbeat_at = now
        row.error = {}
        row.terminal_at = None
    session.flush()
    return row


def heartbeat_workflow_run(
    session: Session,
    *,
    workflow_run_id: str,
    fencing_token: str,
    worker_id: str,
    lease_seconds: int,
) -> None:
    row = session.get(WorkflowRun, workflow_run_id)
    if row is None or row.fencing_token != fencing_token or row.lease_owner != worker_id:
        raise RuntimeError("workflow fencing token is no longer current")
    now = datetime.now(UTC)
    row.heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)


def _attempt_for_stage(
    session: Session,
    *,
    run: WorkflowRun,
    stage: str,
    input_sha256: str,
    output_sha256: str,
) -> WorkflowStageAttempt:
    row = session.scalar(
        select(WorkflowStageAttempt).where(
            WorkflowStageAttempt.workflow_run_id == run.id,
            WorkflowStageAttempt.stage == stage,
            WorkflowStageAttempt.attempt == run.attempt,
        )
    )
    if row is None:
        row = WorkflowStageAttempt(
            id=new_ulid(),
            organization_id=run.organization_id,
            workflow_run_id=run.id,
            stage=stage,
            attempt=run.attempt,
            status="succeeded",
            fencing_token=run.fencing_token,
            input_sha256=input_sha256,
            output_sha256=output_sha256,
            error_detail={},
            terminal_at=datetime.now(UTC),
        )
        session.add(row)
        session.flush()
    return row


def persist_workflow_evidence(
    session: Session,
    *,
    run: WorkflowRun,
    project: Path,
    result: WorkflowResultV2,
) -> WorkflowCheckpointSet:
    for path in sorted((project / "agent" / "turns").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if session.get(WorkflowAgentTurn, payload["turnId"]) is not None:
            continue
        usage = payload.get("usage") or {}
        session.add(
            WorkflowAgentTurn(
                id=payload["turnId"],
                organization_id=run.organization_id,
                workflow_run_id=run.id,
                sequence=int(payload["sequence"]),
                phase_id=payload["phaseId"],
                role=payload["role"],
                status=payload["status"],
                provider=payload["provider"],
                provider_model=payload.get("providerModel"),
                model_version=payload["modelVersion"],
                prompt_version=payload["promptVersion"],
                reference_version=payload["referenceVersion"],
                prompt_sha256=payload["promptSha256"],
                response_sha256=payload.get("responseSha256"),
                decision=payload.get("decision") or {},
                observation_sha256=payload.get("observationSha256"),
                input_tokens=int(usage.get("inputTokens") or 0),
                output_tokens=int(usage.get("outputTokens") or 0),
                cost_microunits=int(usage.get("costMicrounits") or 0),
                elapsed_seconds=float(usage.get("elapsedSeconds") or 0),
                created_at=datetime.fromisoformat(payload["createdAt"]),
            )
        )
    session.flush()
    for path in sorted((project / "agent" / "tool-calls").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if session.get(WorkflowAgentToolCall, payload["toolCallId"]) is not None:
            continue
        author_turn_id = payload.get("authorTurnId")
        if not author_turn_id or session.get(WorkflowAgentTurn, author_turn_id) is None:
            raise RuntimeError("Agent tool evidence is missing its persisted author turn")
        session.add(
            WorkflowAgentToolCall(
                id=payload["toolCallId"],
                organization_id=run.organization_id,
                workflow_run_id=run.id,
                agent_turn_id=author_turn_id,
                stage=payload["stage"],
                current_pnn=payload.get("currentPnn"),
                author_attempt=int(payload["authorAttempt"]),
                tool_name=payload["toolName"],
                status=payload["status"],
                arguments_sha256=payload["argumentsSha256"],
                input_sha256=payload["inputSha256"],
                output_sha256=payload["outputSha256"],
                subject_sha256=payload["subjectSha256"],
                observation=payload["observation"],
                stale=list(payload.get("stale") or []),
                model_version=payload["modelVersion"],
                prompt_version=payload["promptVersion"],
                reference_version=payload["referenceVersion"],
                usage_before=payload.get("usageBefore") or {},
                started_at=datetime.fromisoformat(payload["startedAt"]),
                completed_at=datetime.fromisoformat(payload["completedAt"]),
            )
        )
    session.flush()
    event_path = project / "validation" / "workflow-events.jsonl"
    events = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events_by_stage: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        events_by_stage.setdefault(str(event.get("stage")), []).append(event)
    checkpoint_rows: list[WorkflowCheckpointSet] = []
    for path in sorted((project / "checkpoints").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        existing = session.scalar(
            select(WorkflowCheckpointSet).where(
                WorkflowCheckpointSet.checkpoint_sha256 == payload["checkpointSha256"]
            )
        )
        if existing is not None:
            checkpoint_rows.append(existing)
            continue
        attempt = _attempt_for_stage(
            session,
            run=run,
            stage=payload["stage"],
            input_sha256=payload["inputSha256"],
            output_sha256=payload["outputSha256"],
        )
        row = WorkflowCheckpointSet(
            id=payload["checkpointSetId"],
            organization_id=run.organization_id,
            workflow_run_id=run.id,
            stage_attempt_id=attempt.id,
            sequence=int(payload["sequence"]),
            stage=payload["stage"],
            input_sha256=payload["inputSha256"],
            output_sha256=payload["outputSha256"],
            checkpoint_sha256=payload["checkpointSha256"],
            payload=payload,
        )
        session.add(row)
        session.flush()
        checkpoint_rows.append(row)
    for stage, stage_events in events_by_stage.items():
        if stage not in {
            "attribution_guard",
            "source_import",
            "template_candidates",
            "stage1",
            "template_handoff",
            "stage2",
            "design_spec_gate1",
            "refine_spec",
            "spec_lock_gate2",
            "design_parameters",
            "live_preview",
            "executor_p01",
            "first_page_gate",
            "executor_remaining",
            "final_svg_gate",
            "chart_gate",
            "final_svg_content_gate",
            "notes",
            "animations",
            "visual_review",
            "step7_finalize",
            "step7_export",
            "postflight",
            "pptx_content_gate",
            "narration",
            "publish",
        }:
            continue
        _attempt_for_stage(
            session,
            run=run,
            stage=stage,
            input_sha256=run.request_sha256,
            output_sha256=canonical_sha256(stage_events),
        )
    for path in sorted((project / "validation" / "receipts").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if session.get(WorkflowGateReceipt, payload["receiptId"]) is not None:
            continue
        session.add(
            WorkflowGateReceipt(
                id=payload["receiptId"],
                organization_id=run.organization_id,
                workflow_run_id=run.id,
                kind=payload["kind"],
                status=payload["status"],
                subject_sha256=payload["subjectSha256"],
                payload=payload["payload"],
                payload_sha256=payload["payloadSha256"],
                receipt_sha256=canonical_sha256(payload),
                actor_id=payload.get("actorId"),
                delegated=bool(payload.get("delegated")),
                delegation_scope=list(payload.get("delegationScope") or []),
                policy_version=payload["policyVersion"],
                expires_at=datetime.fromisoformat(payload["expiresAt"]),
                created_at=datetime.fromisoformat(payload["createdAt"]),
            )
        )
        stage = _RECEIPT_STAGES.get(payload["kind"])
        if stage:
            _attempt_for_stage(
                session,
                run=run,
                stage=stage,
                input_sha256=payload["subjectSha256"],
                output_sha256=payload["payloadSha256"],
            )
    if not checkpoint_rows:
        raise RuntimeError("Default workflow produced no persistent checkpoint")
    final_checkpoint = max(checkpoint_rows, key=lambda value: value.sequence)
    run.current_checkpoint_set_id = final_checkpoint.id
    run.stage = result.stage
    run.usage = result.usage.model_dump(by_alias=True, mode="json")
    return final_checkpoint


def link_workflow_artifacts(
    session: Session,
    *,
    run: WorkflowRun,
    checkpoint: WorkflowCheckpointSet,
    artifacts: list[tuple[Artifact, str, str]],
) -> None:
    for artifact, kind, stage in artifacts:
        session.add(
            WorkflowIntermediateArtifact(
                id=new_ulid(),
                organization_id=run.organization_id,
                workflow_run_id=run.id,
                checkpoint_set_id=checkpoint.id,
                artifact_id=artifact.id,
                kind=kind,
                stage=stage,
                input_sha256=run.request_sha256,
                output_sha256=artifact.sha256,
            )
        )


def finish_workflow_run(
    run: WorkflowRun,
    *,
    status: str,
    stage: str,
    error: dict[str, Any] | None = None,
) -> None:
    run.status = status
    run.stage = stage
    run.error = error or {}
    run.terminal_at = datetime.now(UTC)
