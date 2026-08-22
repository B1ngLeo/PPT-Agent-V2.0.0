"""Production publication path for the Default Agentic v2 workflow."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from instant_ppt_domain.artifacts import tenant_object_key
from instant_ppt_domain.effective_spec import persist_initial_effective_revision
from instant_ppt_domain.generation import (
    GenerationCancellationObserved,
    PublishedArtifactSpec,
    cancel_generation_job,
    fail_generation_job,
    publish_generation_result,
    record_compiled_slides,
)
from instant_ppt_domain.models import (
    Artifact,
    GenerationJob,
    GenerationJobSlide,
    GenerationSnapshot,
    ProviderCall,
    WorkflowCheckpointSet,
    WorkflowRun,
)
from instant_ppt_domain.service import (
    canonical_sha256,
    complete_slide,
    heartbeat_job,
    set_job_stage,
    start_next_slide,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_worker.approved_sources import resolve_approved_sources
from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.default_workflow_request import build_default_workflow_request
from instant_ppt_worker.errors import RENDER_FAILED, AdapterError
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.workflow_models import (
    GeneratePptxDefaultRequest,
    WorkflowRequestV2,
    WorkflowResultV2,
)
from instant_ppt_worker.workflow_runtime import (
    begin_workflow_run,
    finish_workflow_run,
    heartbeat_workflow_run,
    link_workflow_artifacts,
    persist_workflow_evidence,
)
from instant_ppt_worker.workflow_supervisor import (
    WorkflowCancelled,
    run_default_workflow_supervised,
)

PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class DefaultWorkflowObjectStore(Protocol):
    def download(self, object_key: str, target: Path, *, max_bytes: int) -> str: ...

    def put_file(self, object_key: str, path: Path, media_type: str) -> None: ...


class DefaultWorkflowInterrupted(RuntimeError):
    """A recoverable process interruption after durable external writes."""


def _scoped_image_environment(
    snapshot: GenerationSnapshot,
    request: WorkflowRequestV2,
) -> dict[str, str]:
    if "ai" not in request.image.usage or "api" not in request.image.ai_path_chain:
        return {}
    configuration = dict(snapshot.payload.get("providerConfiguration", {}).get("image") or {})
    return {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
        "IMAGE_GENERATION_ENABLED": (
            "true" if bool(configuration.get("enabled", False)) else "false"
        ),
        "IMAGE_BACKEND": str(configuration.get("backend") or "openai"),
        "OPENAI_BASE_URL": str(
            configuration.get("baseUrl") or "https://api.openai.com/v1"
        ),
        "OPENAI_MODEL": str(configuration.get("model") or "gpt-image-2"),
        "OPENAI_OUTPUT_FORMAT": str(configuration.get("outputFormat") or "png"),
        "OPENAI_IMAGE_SIZE": str(configuration.get("size") or "1536x1024"),
        "OPENAI_IMAGE_QUALITY": str(configuration.get("quality") or "low"),
        "IMAGE_MAX_PER_DECK": str(int(configuration.get("maxImagesPerDeck") or 0)),
        "IMAGE_COST_MICROUNITS": str(
            int(configuration.get("costMicrounitsPerImage") or 0)
        ),
        "OPENAI_IMAGE_TIMEOUT_SECONDS": os.getenv(
            "OPENAI_IMAGE_TIMEOUT_SECONDS", "300"
        ).strip(),
    }


def _scoped_text_environment(
    snapshot: GenerationSnapshot,
    request: WorkflowRequestV2,
) -> dict[str, str]:
    if "provider-text" not in request.runtime.allowed_tools:
        return {}
    configuration = dict(
        snapshot.payload.get("providerConfiguration", {}).get("planning") or {}
    )
    return {
        "MOONSHOT_API_KEY": os.getenv("MOONSHOT_API_KEY", "").strip(),
        "KIMI_BASE_URL": str(
            configuration.get("baseUrl") or "https://api.moonshot.cn/v1"
        ),
        "KIMI_MODEL": str(configuration.get("model") or request.versions.model),
        "KIMI_PROTOCOL": str(configuration.get("protocol") or "openai"),
        "KIMI_REASONING_EFFORT": str(
            configuration.get("reasoningEffort") or "max"
        ),
        "KIMI_TIMEOUT_SECONDS": str(
            float(configuration.get("timeoutSeconds") or 240)
        ),
        "KIMI_TRANSPORT_MAX_RETRIES": str(
            int(configuration.get("transportMaxRetries") or 1)
        ),
        "KIMI_RETRY_BACKOFF_SECONDS": str(
            float(configuration.get("retryBackoffSeconds") or 2)
        ),
    }


def _persist_image_provider_calls(
    session_factory: sessionmaker[Session],
    *,
    snapshot: GenerationSnapshot,
    workflow_run_id: str,
    project: Path,
) -> dict[str, Any] | None:
    audit_path = project / "analysis" / "image-resource-audit.json"
    if not audit_path.is_file():
        return None
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    model = str(
        snapshot.payload.get("providerConfiguration", {})
        .get("image", {})
        .get("model")
        or "unavailable"
    )
    now = datetime.now(UTC)
    with session_factory.begin() as session:
        for resource in audit.get("resources") or []:
            if resource.get("acquireVia") != "ai":
                continue
            prompt_sha256 = str(resource.get("promptSha256") or "")
            if len(prompt_sha256) != 64:
                continue
            slide_id = str((resource.get("slideIds") or ["deck"])[0])
            call_id = _stable_id(
                f"{workflow_run_id}:image-provider:{slide_id}:{prompt_sha256}"
            )
            if session.get(ProviderCall, call_id) is not None:
                continue
            attempts = list(resource.get("attempts") or [])
            failed_attempt = next(
                (
                    value
                    for value in reversed(attempts)
                    if value.get("status") == "failed"
                ),
                {},
            )
            session.add(
                ProviderCall(
                    id=call_id,
                    organization_id=snapshot.organization_id,
                    draft_id=snapshot.draft_id,
                    provider=str(
                        resource.get("provider")
                        or resource.get("selectedStrategy")
                        or resource.get("selectedPath")
                        or "image-acquisition"
                    ),
                    model=str(resource.get("model") or model),
                    purpose="default_workflow_image_generate",
                    request_hash=prompt_sha256,
                    status=(
                        "succeeded" if resource.get("status") == "Generated" else "failed"
                    ),
                    input_tokens=0,
                    output_tokens=0,
                    repair_count=0,
                    error_code=(
                        None
                        if resource.get("status") == "Generated"
                        else str(
                            failed_attempt.get("errorCode")
                            or resource.get("failureCode")
                            or "image_acquisition_unresolved"
                        )[:80]
                    ),
                    started_at=now,
                    finished_at=now,
                )
            )
    return audit


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_canonical(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _stable_id(seed: str) -> str:
    return deterministic_ulid(hashlib.sha256(seed.encode("utf-8")).hexdigest())


def _artifact_spec(
    *,
    job_id: str,
    organization_id: str,
    publication_version: int,
    kind: str,
    path: Path,
    media_type: str,
    slide_id: str | None = None,
) -> PublishedArtifactSpec:
    identity = f"{job_id}:v{publication_version}:{kind}:{slide_id or 'deck'}"
    artifact_id = _stable_id(identity)
    return PublishedArtifactSpec(
        artifact_id=artifact_id,
        kind=kind,
        object_key=tenant_object_key(organization_id, "published", artifact_id),
        sha256=sha256_file(path),
        media_type=media_type,
        size_bytes=path.stat().st_size,
        slide_id=slide_id,
    )


def _load_generation(
    session: Session,
    job_id: str,
    organization_id: str,
) -> tuple[GenerationJob, GenerationSnapshot, list[GenerationJobSlide]]:
    job = session.scalar(
        select(GenerationJob).where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == organization_id,
        )
    )
    if job is None or job.processor != "real":
        raise RuntimeError("real generation job is unavailable")
    snapshot = session.scalar(
        select(GenerationSnapshot).where(
            GenerationSnapshot.id == job.snapshot_id,
            GenerationSnapshot.organization_id == organization_id,
        )
    )
    if snapshot is None:
        raise RuntimeError("generation snapshot is unavailable")
    slides = list(
        session.scalars(
            select(GenerationJobSlide)
            .where(GenerationJobSlide.job_id == job.id)
            .order_by(GenerationJobSlide.position)
        )
    )
    return job, snapshot, slides


def _publish_files(
    store: DefaultWorkflowObjectStore,
    values: list[tuple[PublishedArtifactSpec, Path]],
) -> None:
    for spec, path in values:
        store.put_file(spec.object_key, path, spec.media_type)


def _fail_default_run(
    session_factory: sessionmaker[Session],
    *,
    job_id: str,
    organization_id: str,
    worker_id: str,
    workflow_run_id: str,
    error_code: str,
    message: str,
    worker_seconds: int,
) -> None:
    with session_factory.begin() as session:
        run = session.get(WorkflowRun, workflow_run_id)
        if run is not None:
            finish_workflow_run(
                run,
                status="failed",
                stage=run.stage,
                error={"code": error_code, "message": message[-1000:]},
            )
        fail_generation_job(
            session,
            job_id=job_id,
            organization_id=organization_id,
            worker_id=worker_id,
            error_code=error_code,
            worker_seconds=worker_seconds,
        )


def _process_default_generation_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    worker_id: str,
    *,
    organization_id: str,
    lease_seconds: int,
    object_store: DefaultWorkflowObjectStore,
    started: float,
    before_publish_callback: Callable[[], None] | None = None,
) -> str:
    with tempfile.TemporaryDirectory(prefix="instant-ppt-default-") as temporary:
        root = Path(temporary)
        with session_factory() as session:
            job, snapshot, slides = _load_generation(session, job_id, organization_id)
            source_manifest = resolve_approved_sources(
                session,
                snapshot,
                object_store=object_store,
                workspace=root / "approved-sources",
            )
        workflow_run_id = _stable_id(f"{job_id}:default-agentic-workflow")
        request = build_default_workflow_request(
            snapshot,
            slides,
            workflow_run_id=workflow_run_id,
            sources=source_manifest.model_dump(by_alias=True, mode="json"),
        )
        request_sha256 = canonical_sha256(request.model_dump(by_alias=True, mode="json"))
        with session_factory.begin() as session:
            locked_job, locked_snapshot, _ = _load_generation(
                session,
                job_id,
                organization_id,
            )
            run = begin_workflow_run(
                session,
                job=locked_job,
                snapshot=locked_snapshot,
                request=request,
                request_sha256=request_sha256,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
            fencing_token = str(run.fencing_token)

        def cancellation_requested() -> bool:
            with session_factory() as session:
                current = session.get(GenerationJob, job_id)
                return current is None or current.status == "cancel_requested"

        def heartbeat() -> None:
            with session_factory.begin() as session:
                heartbeat_job(session, job_id, worker_id, lease_seconds=lease_seconds)
                heartbeat_workflow_run(
                    session,
                    workflow_run_id=workflow_run_id,
                    fencing_token=fencing_token,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )

        adapter_request = GeneratePptxDefaultRequest(
            schema_version=2,
            request_id=f"{job_id}-default-v2",
            operation="generatePptxDefault",
            workspace_root=str(root),
            output_key=f"projects/job-{job_id[-8:]}",
            workflow=request,
        )
        try:
            supervised = run_default_workflow_supervised(
                root,
                adapter_request,
                hard_timeout_seconds=request.runtime.hard_timeout_seconds,
                cancellation_requested=cancellation_requested,
                heartbeat=heartbeat,
                text_environment=_scoped_text_environment(snapshot, request),
                image_environment=_scoped_image_environment(snapshot, request),
            )
        except WorkflowCancelled:
            worker_seconds = max(1, math.ceil(time.monotonic() - started))
            with session_factory.begin() as session:
                run = session.get(WorkflowRun, workflow_run_id)
                if run is not None:
                    finish_workflow_run(run, status="cancelled", stage=run.stage)
                cancel_generation_job(
                    session,
                    job_id=job_id,
                    organization_id=organization_id,
                    worker_id=worker_id,
                    worker_seconds=worker_seconds,
                )
            return "cancelled"
        except (AdapterError, OSError, RuntimeError, ValueError) as error:
            worker_seconds = max(1, math.ceil(time.monotonic() - started))
            code = error.code if isinstance(error, AdapterError) else RENDER_FAILED
            _fail_default_run(
                session_factory,
                job_id=job_id,
                organization_id=organization_id,
                worker_id=worker_id,
                workflow_run_id=workflow_run_id,
                error_code=code,
                message=str(error),
                worker_seconds=worker_seconds,
            )
            return "failed"

        project = supervised.project
        result = WorkflowResultV2.model_validate_json(
            (project / "workflow-result.json").read_text(encoding="utf-8")
        )
        image_audit = _persist_image_provider_calls(
            session_factory,
            snapshot=snapshot,
            workflow_run_id=workflow_run_id,
            project=project,
        )
        if result.status != "succeeded" or result.request_sha256 != request_sha256:
            worker_seconds = max(1, math.ceil(time.monotonic() - started))
            if result.request_sha256 == request_sha256 and result.status == "needs_manual":
                with session_factory.begin() as session:
                    run = session.get(WorkflowRun, workflow_run_id)
                    if run is not None:
                        persist_workflow_evidence(
                            session,
                            run=run,
                            project=project,
                            result=result,
                        )
                        finish_workflow_run(
                            run,
                            status="needs_manual",
                            stage=result.stage,
                            error={
                                "code": result.errors[0].code if result.errors else "needs_manual",
                                "message": (
                                    result.errors[0].message
                                    if result.errors
                                    else "workflow requires manual image fulfillment"
                                ),
                            },
                        )
                    fail_generation_job(
                        session,
                        job_id=job_id,
                        organization_id=organization_id,
                        worker_id=worker_id,
                        error_code=(
                            result.errors[0].code
                            if result.errors
                            else "workflow_needs_manual"
                        ),
                        worker_seconds=worker_seconds,
                    )
                return "needs_manual"
            _fail_default_run(
                session_factory,
                job_id=job_id,
                organization_id=organization_id,
                worker_id=worker_id,
                workflow_run_id=workflow_run_id,
                error_code="workflow_incomplete",
                message=f"Default workflow stopped in {result.status}/{result.stage}",
                worker_seconds=worker_seconds,
            )
            return "failed"
        with session_factory.begin() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None or run.fencing_token != fencing_token:
                raise RuntimeError("workflow fencing token changed before evidence persistence")
            checkpoint = persist_workflow_evidence(
                session,
                run=run,
                project=project,
                result=result,
            )
            checkpoint_id = checkpoint.id

        deck = json.loads((project / "deck-plan.json").read_text(encoding="utf-8"))
        authored_slides = list(deck["slides"])
        final_svgs = sorted((project / "svg_final").glob("*.svg"))
        if len(authored_slides) != len(slides) or len(final_svgs) != len(slides):
            raise RuntimeError("Default workflow output roster does not match the approved roster")
        compiled: dict[str, tuple[str, dict[str, Any]]] = {}
        for authored, path in zip(authored_slides, final_svgs, strict=True):
            with session_factory.begin() as session:
                heartbeat_job(session, job_id, worker_id, lease_seconds=lease_seconds)
                current = session.scalar(
                    select(GenerationJobSlide).where(
                        GenerationJobSlide.job_id == job_id,
                        GenerationJobSlide.slide_id == authored["slideId"],
                    )
                )
                if current is None:
                    raise RuntimeError("Default workflow slide disappeared")
                svg_sha256 = sha256_file(path)
                gate_payload = {
                    "workflowRunId": workflow_run_id,
                    "checkpointSetId": checkpoint_id,
                    "finalSvgSha256": svg_sha256,
                    "contentGate": "passed",
                    "wholeDeckFinalGate": "passed",
                }
                if current.status == "ready":
                    current.title = authored["title"]
                    current.body = list(authored["body"])
                    current.artifact_ref = f"workflow://{workflow_run_id}/{path.name}"
                    current.render_sha256 = svg_sha256
                    current.qa_report = gate_payload
                    compiled[current.slide_id] = (svg_sha256, gate_payload)
                    continue
                slide_start = start_next_slide(session, job_id, worker_id)
                if slide_start is None or slide_start.slide_id != authored["slideId"]:
                    raise RuntimeError("Default workflow slide identity changed during publication")
                current.title = authored["title"]
                current.body = list(authored["body"])
                complete_slide(
                    session,
                    job_id,
                    current.slide_id,
                    worker_id,
                    succeeded=True,
                    artifact_ref=f"workflow://{workflow_run_id}/{path.name}",
                    render_sha256=svg_sha256,
                    qa_report=gate_payload,
                )
                compiled[current.slide_id] = (svg_sha256, gate_payload)
        with session_factory.begin() as session:
            set_job_stage(session, job_id, worker_id, "deck_qa")
            set_job_stage(session, job_id, worker_id, "compiling")
            record_compiled_slides(
                session,
                job_id=job_id,
                organization_id=organization_id,
                worker_id=worker_id,
                compiled=compiled,
            )
            heartbeat_job(session, job_id, worker_id, lease_seconds=lease_seconds)

        with session_factory() as session:
            job, snapshot, slides = _load_generation(session, job_id, organization_id)
        publication_version = job.publication_version + 1
        presentation_id = _stable_id(f"{job_id}:presentation")
        presentation_revision_id = _stable_id(
            f"{job_id}:presentation-revision:{publication_version}"
        )
        design_content = json.loads(
            (project / "validation" / "content-design-spec.json").read_text(
                encoding="utf-8"
            )
        )
        final_svg_content = json.loads(
            (project / "validation" / "content-final-svg.json").read_text(
                encoding="utf-8"
            )
        )
        compiled_pptx_content = json.loads(
            (project / "validation" / "content-pptx.json").read_text(encoding="utf-8")
        )
        content_reports = [design_content, final_svg_content, compiled_pptx_content]
        content_reports_current = all(
            report.get("passed") is True
            and report.get("reportSha256")
            == canonical_sha256(
                {key: value for key, value in report.items() if key != "reportSha256"}
            )
            for report in content_reports
        )
        if not content_reports_current:
            raise RuntimeError("content release reports are failed, missing, or hash-stale")
        evidence_map = json.loads(
            (project / "analysis" / "evidence-map.json").read_text(encoding="utf-8")
        )
        content_mode = (
            "source-grounded"
            if source_manifest.artifacts
            else "limited-general-draft"
        )
        qa_payload = {
            "schemaVersion": 2,
            "workflowRunId": workflow_run_id,
            "requestSha256": request_sha256,
            "sourceManifestSha256": source_manifest.manifest_sha256,
            "evidenceMapSha256": evidence_map["evidenceMapSha256"],
            "contentMode": content_mode,
            "exactRoster": [item.pnn for item in request.outline],
            "designSpecContent": design_content,
            "finalSvgContent": final_svg_content,
            "compiledPptxContent": compiled_pptx_content,
            "passed": content_reports_current,
        }
        qa_path = root / "generation-qa-report.json"
        _write_canonical(qa_path, qa_payload)
        artifact_values: list[tuple[str, Path, str, str | None]] = [
            (
                "generation_source_bundle",
                project / "canonical-project-bundle.zip",
                "application/zip",
                None,
            ),
            ("generation_baseline_pptx", project / "exports" / "deck.pptx", PPTX_MEDIA_TYPE, None),
            ("generation_preview_svg", final_svgs[0], "image/svg+xml", None),
            ("generation_qa_report", qa_path, "application/json", None),
            ("generation_design_spec", project / "design_spec.md", "text/markdown", None),
            ("generation_spec_lock", project / "spec_lock.md", "text/markdown", None),
            (
                "generation_evidence_map",
                project / "analysis" / "evidence-map.json",
                "application/json",
                None,
            ),
            (
                "generation_workflow_result",
                project / "workflow-result.json",
                "application/json",
                None,
            ),
            (
                "generation_final_svg_qa",
                project / "validation" / "svg_quality_report.json",
                "application/json",
                None,
            ),
            (
                "generation_package_qa",
                project / "validation" / "pptx-package-qa.json",
                "application/json",
                None,
            ),
        ]
        artifact_values.extend(
            (
                "generation_slide_svg",
                path,
                "image/svg+xml",
                slide.slide_id,
            )
            for slide, path in zip(slides, final_svgs, strict=True)
        )
        image_analysis_path = project / "analysis" / "image_analysis.csv"
        image_audit_path = project / "analysis" / "image-resource-audit.json"
        image_prompt_path = project / "images" / "image_prompts.json"
        if image_analysis_path.is_file():
            artifact_values.append(
                ("generation_image_analysis", image_analysis_path, "text/csv", None)
            )
        if image_audit_path.is_file():
            artifact_values.append(
                ("generation_image_audit", image_audit_path, "application/json", None)
            )
        if image_prompt_path.is_file():
            artifact_values.append(
                ("generation_image_prompts", image_prompt_path, "application/json", None)
            )
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        image_slide_ids = {
            str(resource.get("filename")): str((resource.get("slideIds") or [""])[0])
            for resource in (image_audit or {}).get("resources", [])
            if resource.get("filename")
        }
        for path in sorted((project / "images").glob("*")):
            media_type = media_types.get(path.suffix.lower())
            if media_type is None:
                continue
            artifact_values.append(
                (
                    "generation_image_asset",
                    path,
                    media_type,
                    image_slide_ids.get(path.name) or None,
                )
            )
        specs_and_paths = [
            (
                _artifact_spec(
                    job_id=job_id,
                    organization_id=organization_id,
                    publication_version=publication_version,
                    kind=kind,
                    path=path,
                    media_type=media_type,
                    slide_id=slide_id,
                ),
                path,
            )
            for kind, path, media_type, slide_id in artifact_values
        ]
        spec_by_kind = {spec.kind: spec for spec, _ in specs_and_paths if spec.slide_id is None}
        slide_specs = {
            spec.slide_id: spec
            for spec, _ in specs_and_paths
            if spec.kind == "generation_slide_svg" and spec.slide_id
        }
        effective_id = _stable_id(f"{presentation_revision_id}:effective-spec:1")
        evidence_by_slide = {
            str(value["slideId"]): value for value in evidence_map["slides"]
        }
        roster = [
            {
                "pnn": outline.pnn,
                "slideId": slide.slide_id,
                "outlineSlideId": slide.outline_slide_id,
                "position": slide.position,
                "role": outline.role,
                "title": slide.title,
                "body": list(slide.body),
                "artifactId": slide_specs[slide.slide_id].artifact_id,
                "chart": evidence_by_slide[slide.slide_id].get("chart"),
            }
            for outline, slide in zip(request.outline, slides, strict=True)
        ]
        canonical_artifacts = {
            "pptxArtifactId": spec_by_kind["generation_baseline_pptx"].artifact_id,
            "pptxSha256": spec_by_kind["generation_baseline_pptx"].sha256,
            "bundleArtifactId": spec_by_kind["generation_source_bundle"].artifact_id,
            "bundleSha256": spec_by_kind["generation_source_bundle"].sha256,
            "designSpecArtifactId": spec_by_kind["generation_design_spec"].artifact_id,
            "specLockArtifactId": spec_by_kind["generation_spec_lock"].artifact_id,
            "evidenceMapArtifactId": spec_by_kind["generation_evidence_map"].artifact_id,
            "evidenceMapSha256": evidence_map["evidenceMapSha256"],
            "contentQaArtifactId": spec_by_kind["generation_qa_report"].artifact_id,
            "contentQaSha256": spec_by_kind["generation_qa_report"].sha256,
            "finalSvgReportSha256": spec_by_kind["generation_final_svg_qa"].sha256,
            "packageQaSha256": spec_by_kind["generation_package_qa"].sha256,
        }
        if "generation_image_audit" in spec_by_kind:
            canonical_artifacts["imageAuditArtifactId"] = spec_by_kind[
                "generation_image_audit"
            ].artifact_id
            canonical_artifacts["imageAuditSha256"] = spec_by_kind[
                "generation_image_audit"
            ].sha256
        manifest_artifact_id = _stable_id(
            f"{job_id}:v{publication_version}:generation_manifest:deck"
        )
        manifest_object_key = tenant_object_key(
            organization_id,
            "published",
            manifest_artifact_id,
        )
        manifest_payload = {
            "schemaVersion": 2,
            "artifactId": manifest_artifact_id,
            "artifactType": "generation_manifest",
            "organizationId": organization_id,
            "objectKey": manifest_object_key,
            "jobId": job_id,
            "snapshotId": snapshot.id,
            "snapshotSha256": snapshot.snapshot_sha256,
            "workflowRunId": workflow_run_id,
            "workflowRequestSha256": request_sha256,
            "engineProfile": "default-agentic",
            "route": "generate_pptx",
            "contentMode": content_mode,
            "sourceGroundingStatus": (
                "verified" if source_manifest.artifacts else "not-applicable-limited-draft"
            ),
            "publicationVersion": publication_version,
            "presentationId": presentation_id,
            "presentationRevisionId": presentation_revision_id,
            "effectiveSpecRevisionId": effective_id,
            "sourceManifestSha256": source_manifest.manifest_sha256,
            "exactRoster": [value["pnn"] for value in roster],
            "imageGeneration": (
                {
                    "status": "succeeded",
                    "scope": image_audit["imageScope"],
                    "usage": image_audit["imageUsage"],
                    "imageCount": result.usage.image_count,
                    "generatedCount": image_audit["generatedCount"],
                    "costMicrounits": image_audit["costMicrounits"],
                    "auditSha256": image_audit["auditSha256"],
                }
                if image_audit is not None
                else {"status": "disabled", "imageCount": 0}
            ),
            "artifacts": [
                {
                    "artifactId": spec.artifact_id,
                    "artifactType": spec.kind,
                    "objectKey": spec.object_key,
                    "sha256": spec.sha256,
                    "mediaType": spec.media_type,
                    "sizeBytes": spec.size_bytes,
                    "slideId": spec.slide_id,
                }
                for spec, _ in specs_and_paths
            ],
        }
        manifest_path = root / "generation-manifest.json"
        _write_canonical(manifest_path, manifest_payload)
        manifest_spec = PublishedArtifactSpec(
            artifact_id=manifest_artifact_id,
            kind="generation_manifest",
            object_key=manifest_object_key,
            sha256=sha256_file(manifest_path),
            media_type="application/json",
            size_bytes=manifest_path.stat().st_size,
        )
        specs_and_paths.append((manifest_spec, manifest_path))
        _publish_files(object_store, specs_and_paths)
        if before_publish_callback is not None:
            try:
                before_publish_callback()
            except Exception as error:
                raise DefaultWorkflowInterrupted(
                    "Default worker was interrupted after artifact upload"
                ) from error
        worker_seconds = max(1, math.ceil(time.monotonic() - started))
        try:
            with session_factory.begin() as session:
                set_job_stage(session, job_id, worker_id, "publishing")
                _, _, revision = publish_generation_result(
                    session,
                    job_id=job_id,
                    organization_id=organization_id,
                    worker_id=worker_id,
                    publication_version=publication_version,
                    artifacts=[spec for spec, _ in specs_and_paths],
                    manifest_artifact_id=manifest_artifact_id,
                    manifest_payload=manifest_payload,
                    presentation_id=presentation_id,
                    presentation_revision_id=presentation_revision_id,
                    worker_seconds=worker_seconds,
                )
                persist_initial_effective_revision(
                    session,
                    organization_id=organization_id,
                    workflow_run_id=workflow_run_id,
                    presentation_revision_id=revision.id,
                    design_spec_sha256=spec_by_kind["generation_design_spec"].sha256,
                    spec_lock_sha256=spec_by_kind["generation_spec_lock"].sha256,
                    source_manifest_sha256=source_manifest.manifest_sha256,
                    roster=roster,
                    canonical_artifacts=canonical_artifacts,
                    effective_spec_revision_id=effective_id,
                )
                run = session.get(WorkflowRun, workflow_run_id)
                if run is None or run.current_checkpoint_set_id != checkpoint_id:
                    raise RuntimeError("workflow checkpoint changed before publication")
                intermediate: list[tuple[Artifact, str, str]] = []
                for spec, _ in specs_and_paths:
                    artifact = session.get(Artifact, spec.artifact_id)
                    if artifact is None:
                        raise RuntimeError("published workflow artifact is missing")
                    stage = {
                        "generation_design_spec": "design_spec_gate1",
                        "generation_spec_lock": "spec_lock_gate2",
                        "generation_final_svg_qa": "final_svg_gate",
                        "generation_package_qa": "postflight",
                        "generation_baseline_pptx": "step7_export",
                    }.get(spec.kind, "publish")
                    intermediate.append((artifact, spec.kind, stage))
                checkpoint = run.current_checkpoint_set_id
                if checkpoint is None:
                    raise RuntimeError("workflow final checkpoint is missing")
                checkpoint_row = session.get(WorkflowCheckpointSet, checkpoint)
                if checkpoint_row is None:
                    raise RuntimeError("workflow final checkpoint row is missing")
                link_workflow_artifacts(
                    session,
                    run=run,
                    checkpoint=checkpoint_row,
                    artifacts=intermediate,
                )
                finish_workflow_run(run, status="succeeded", stage="publish")
        except GenerationCancellationObserved:
            with session_factory.begin() as session:
                run = session.get(WorkflowRun, workflow_run_id)
                if run is not None:
                    finish_workflow_run(run, status="cancelled", stage="publish")
                cancel_generation_job(
                    session,
                    job_id=job_id,
                    organization_id=organization_id,
                    worker_id=worker_id,
                    worker_seconds=worker_seconds,
                )
            return "cancelled"
    return "succeeded"


def process_default_generation_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    worker_id: str,
    *,
    organization_id: str,
    lease_seconds: int,
    object_store: DefaultWorkflowObjectStore,
    started: float,
    before_publish_callback: Callable[[], None] | None = None,
) -> str:
    """Converge unknown failures while preserving intentional crash recovery."""

    try:
        return _process_default_generation_job(
            session_factory,
            job_id,
            worker_id,
            organization_id=organization_id,
            lease_seconds=lease_seconds,
            object_store=object_store,
            started=started,
            before_publish_callback=before_publish_callback,
        )
    except DefaultWorkflowInterrupted as error:
        if error.__cause__ is not None:
            raise error.__cause__ from None
        raise
    except Exception as error:
        workflow_run_id = _stable_id(f"{job_id}:default-agentic-workflow")
        _fail_default_run(
            session_factory,
            job_id=job_id,
            organization_id=organization_id,
            worker_id=worker_id,
            workflow_run_id=workflow_run_id,
            error_code=RENDER_FAILED,
            message=str(error),
            worker_seconds=max(1, math.ceil(time.monotonic() - started)),
        )
        return "failed"
