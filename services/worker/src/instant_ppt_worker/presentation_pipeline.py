"""G07 asynchronous slide regeneration, exact-revision export, and cleanup workers."""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from instant_ppt_domain.artifacts import tenant_object_key
from instant_ppt_domain.effective_spec import (
    compile_operations,
    persist_compilation,
)
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    DataExport,
    DesignSpecEditPatch,
    Draft,
    EffectiveDesignSpecRevision,
    ExportJob,
    GenerationArtifact,
    GenerationJob,
    GenerationSnapshot,
    Presentation,
    PresentationRevision,
    ProjectCleanupJob,
    SlideRegenerationJob,
    SlideVersion,
    Source,
    SourceArtifact,
    UsageLedger,
)
from instant_ppt_domain.presentation import canonical_bytes
from instant_ppt_domain.service import canonical_sha256
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_worker.approved_sources import resolve_approved_sources
from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.errors import AdapterError
from instant_ppt_worker.generation_pipeline import _run_adapter, _template_binding
from instant_ppt_worker.grounding_quality import build_evidence_map
from instant_ppt_worker.models import DeckPlan
from instant_ppt_worker.renderer import render_revision_deck, render_slide_candidate
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.source_pipeline import WorkerObjectSettings, WorkerObjectStore

PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
EFFECTIVE_ROLE_MAP = {
    "cover": "cover",
    "section": "section",
    "data": "data",
    "comparison": "comparison",
    "timeline": "timeline",
    "risk_action": "risk_action",
    "ending": "ending",
}


class PresentationObjectStore(Protocol):
    def download(self, object_key: str, target: Path, *, max_bytes: int) -> str: ...

    def put_file(self, object_key: str, path: Path, media_type: str) -> None: ...

    def remove(self, object_key: str) -> None: ...


def _stable_id(seed: str) -> str:
    return deterministic_ulid(hashlib.sha256(seed.encode("utf-8")).hexdigest())


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value))


def _deck_plan(
    snapshot: GenerationSnapshot,
    presentation: Presentation,
    slides: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "snapshotId": snapshot.id,
        "title": presentation.title,
        "modeId": "native",
        "templateBinding": _template_binding(snapshot),
        "slides": [
            {
                "schemaVersion": 1,
                "slideId": slide["slideId"],
                "outlineSlideId": slide["outlineSlideId"],
                "order": index,
                "role": slide.get("role") or ("cover" if index == 0 else "content"),
                "title": slide["title"],
                "body": (
                    ["；".join(slide["body"])]
                    if index == 0 and len(slide["body"]) > 1
                    else slide["body"] or ["内容待补充"]
                ),
                "editable": True,
            }
            for index, slide in enumerate(slides)
        ],
    }


def _effective_revision(
    session: Session, revision: PresentationRevision
) -> EffectiveDesignSpecRevision | None:
    row = session.scalar(
        select(EffectiveDesignSpecRevision).where(
            EffectiveDesignSpecRevision.presentation_revision_id == revision.id
        )
    )
    if row is None and revision.payload.get("effectiveSpecRevisionId"):
        row = session.get(EffectiveDesignSpecRevision, revision.payload["effectiveSpecRevisionId"])
    return row


def _effective_deck_plan(
    snapshot: GenerationSnapshot,
    presentation: Presentation,
    effective: EffectiveDesignSpecRevision,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "snapshotId": snapshot.id,
        "title": presentation.title,
        "modeId": "native",
        "templateBinding": _template_binding(snapshot),
        "slides": [
            {
                "schemaVersion": 1,
                "slideId": slide["slideId"],
                "outlineSlideId": slide["outlineSlideId"],
                "order": index,
                "role": EFFECTIVE_ROLE_MAP.get(str(slide["role"]), "content"),
                "title": slide["title"],
                "body": (
                    ["；".join(slide["body"])]
                    if slide["role"] == "cover" and len(slide["body"]) > 1
                    else slide["body"]
                ),
                "editable": True,
            }
            for index, slide in enumerate(effective.roster)
        ],
    }


def _source_fragments(source_manifest: Any) -> list[dict[str, Any]]:
    return [
        {
            "sourceArtifactId": artifact.source_artifact_id,
            "sourceId": artifact.source_id,
            "objectSha256": artifact.object_sha256,
            "fragmentId": fragment.fragment_id,
            "page": fragment.page,
            "kind": fragment.kind,
            "text": fragment.text,
            "textSha256": fragment.text_sha256,
            "taint": "untrusted-source-data",
        }
        for artifact in source_manifest.artifacts
        for fragment in artifact.fragments
    ]


def _revision_evidence(
    session: Session,
    snapshot: GenerationSnapshot,
    effective: EffectiveDesignSpecRevision,
    deck: DeckPlan,
    *,
    object_store: PresentationObjectStore,
    workspace: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    source_manifest = resolve_approved_sources(
        session,
        snapshot,
        object_store=object_store,
        workspace=workspace / "approved-sources",
    )
    expected_manifest_sha256 = str(effective.payload.get("sourceManifestSha256") or "")
    if source_manifest.manifest_sha256 != expected_manifest_sha256:
        raise AdapterError(
            "CONTENT_QA_FAILED",
            "Effective Design Spec source manifest binding is stale",
        )
    fragments = _source_fragments(source_manifest)
    evidence_map = build_evidence_map(
        deck,
        effective.roster,
        fragments,
        source_manifest_sha256=source_manifest.manifest_sha256,
    )
    chain_ids: list[str] = []
    cursor: EffectiveDesignSpecRevision | None = effective
    while cursor is not None:
        chain_ids.append(cursor.id)
        if cursor.based_on_id is None:
            break
        cursor = session.get(EffectiveDesignSpecRevision, cursor.based_on_id)
    patches = list(
        session.scalars(
            select(DesignSpecEditPatch)
            .where(DesignSpecEditPatch.effective_spec_revision_id.in_(chain_ids))
            .order_by(DesignSpecEditPatch.created_at, DesignSpecEditPatch.sequence)
        )
    )
    patches_by_slide: dict[str, list[DesignSpecEditPatch]] = {}
    for patch in patches:
        patches_by_slide.setdefault(patch.slide_id, []).append(patch)
    for slide in evidence_map["slides"]:
        slide_patches = patches_by_slide.get(str(slide["slideId"]), [])
        if not slide_patches:
            continue
        audit = {
            "classification": "user-authored-analysis",
            "patchSha256s": [patch.patch_sha256 for patch in slide_patches],
            "actorIds": sorted({patch.actor_id for patch in slide_patches}),
        }
        for claim in slide["claims"]:
            claim["claimType"] = "user-authored-analysis"
            claim["citations"] = []
            claim.pop("derivation", None)
            claim["audit"] = audit
    evidence_map["revisionBinding"] = {
        "effectiveSpecRevisionId": effective.id,
        "effectiveSpecInputSha256": effective.effective_spec_sha256,
        "specLockSha256": effective.spec_lock_sha256,
        "patchSha256s": [patch.patch_sha256 for patch in patches],
    }
    evidence_map["evidenceMapSha256"] = canonical_sha256(
        {
            key: value
            for key, value in evidence_map.items()
            if key != "evidenceMapSha256"
        }
    )
    return evidence_map, fragments, source_manifest.manifest_sha256


def _artifact(
    *,
    artifact_id: str,
    organization_id: str,
    artifact_type: str,
    path: Path,
    media_type: str,
) -> Artifact:
    return Artifact(
        id=artifact_id,
        organization_id=organization_id,
        artifact_type=artifact_type,
        partition="published",
        object_key=tenant_object_key(organization_id, "published", artifact_id),
        sha256=sha256_file(path),
        media_type=media_type,
        size_bytes=path.stat().st_size,
        status="published",
        retention_expires_at=datetime.now(UTC) + timedelta(days=30),
    )


def _slide_values(row: SlideVersion) -> dict[str, Any]:
    return {
        "slideId": row.slide_id,
        "outlineSlideId": row.outline_slide_id,
        "position": row.position,
        "status": row.status,
        "title": row.title,
        "body": list(row.body),
        "artifactId": row.artifact_id,
        "errorCode": row.error_code,
        "sourceSlideVersionId": row.id,
    }


def process_slide_regeneration(
    session_factory: sessionmaker[Session],
    job_id: str,
    organization_id: str,
    *,
    object_store: PresentationObjectStore | None = None,
) -> str:
    store = object_store or WorkerObjectStore(WorkerObjectSettings.from_env())
    with session_factory.begin() as session:
        job = session.scalar(
            select(SlideRegenerationJob)
            .where(
                SlideRegenerationJob.id == job_id,
                SlideRegenerationJob.organization_id == organization_id,
            )
            .with_for_update()
        )
        if job is None:
            return "noop_missing"
        if job.status in {"succeeded", "failed", "cancelled"}:
            return f"noop_{job.status}"
        presentation = session.scalar(
            select(Presentation).where(
                Presentation.id == job.presentation_id,
                Presentation.organization_id == organization_id,
                Presentation.deleted_at.is_(None),
            )
        )
        if presentation is None:
            job.status = "cancelled"
            job.terminal_at = datetime.now(UTC)
            return "cancelled"
        base = session.get(PresentationRevision, job.base_revision_id)
        if base is None:
            job.status = "failed"
            job.error_code = "base_revision_missing"
            job.terminal_at = datetime.now(UTC)
            return "failed"
        source_slides = list(
            session.scalars(
                select(SlideVersion)
                .where(SlideVersion.presentation_revision_id == base.id)
                .order_by(SlideVersion.position)
            )
        )
        target = next((row for row in source_slides if row.slide_id == job.slide_id), None)
        snapshot = session.get(GenerationSnapshot, base.snapshot_id)
        if target is None or snapshot is None:
            job.status = "failed"
            job.error_code = "regeneration_input_missing"
            job.terminal_at = datetime.now(UTC)
            return "failed"
        effective = _effective_revision(session, base)
        effective_revision_id = (
            _stable_id(f"regeneration:{job.id}:effective-spec") if effective else None
        )
        target_role = "cover" if target.position == 1 else "content"
        target_index = target.position
        if effective is not None:
            effective_target = next(
                (slide for slide in effective.roster if slide["slideId"] == target.slide_id),
                None,
            )
            if effective_target is None:
                job.status = "failed"
                job.error_code = "effective_roster_slide_missing"
                job.terminal_at = datetime.now(UTC)
                return "failed"
            target_role = EFFECTIVE_ROLE_MAP.get(str(effective_target["role"]), "content")
            target_index = next(
                index
                for index, slide in enumerate(effective.roster, start=1)
                if slide["slideId"] == target.slide_id
            )
            whole_plan = _effective_deck_plan(snapshot, presentation, effective)
        else:
            whole_plan = _deck_plan(
                snapshot,
                presentation,
                [_slide_values(slide) for slide in source_slides],
            )
        job.status = "running"
        job.attempt += 1
        instruction = job.instruction

    new_title = target.title
    # Instructions are private model inputs/audit data. The legacy renderer cannot
    # faithfully apply them, so it preserves approved visible copy instead of leaking
    # prompts or fabricated QA claims into the slide. The Default workflow replaces
    # this compatibility behavior with an EffectiveDesignSpecRevision patch.
    new_body = list(target.body)
    candidate = {
        "slideId": target.slide_id,
        "outlineSlideId": target.outline_slide_id,
        "title": new_title,
        "body": new_body,
        "role": target_role,
    }
    for whole_slide in whole_plan["slides"]:
        if whole_slide["slideId"] == target.slide_id:
            whole_slide["title"] = new_title
            whole_slide["body"] = new_body
    artifact_id = _stable_id(f"regeneration:{job_id}:slide")
    manifest_id = _stable_id(f"regeneration:{job_id}:manifest")
    revision_id = _stable_id(f"regeneration:{job_id}:revision")
    try:
        with tempfile.TemporaryDirectory(prefix="instant-ppt-regeneration-") as temporary:
            root = Path(temporary)
            plan = DeckPlan.model_validate(_deck_plan(snapshot, presentation, [candidate]))
            rendered = render_slide_candidate(plan, root / "candidate", visual_index=0)
            candidate_qa = json.loads(rendered["qa"].read_text(encoding="utf-8"))
            if effective is not None:
                whole_rendered = root / "regeneration-whole-deck"
                whole_deck = DeckPlan.model_validate(whole_plan)
                with session_factory() as grounding_session:
                    grounding_effective = grounding_session.get(
                        EffectiveDesignSpecRevision, effective.id
                    )
                    revision_evidence, source_fragments, source_manifest_sha256 = (
                        _revision_evidence(
                            grounding_session,
                            snapshot,
                            grounding_effective,
                            whole_deck,
                            object_store=store,
                            workspace=root / "regeneration-grounding",
                        )
                    )
                render_revision_deck(
                    whole_deck,
                    whole_rendered,
                    chart_specs={
                        str(slide["slideId"]): dict(slide["chart"])
                        for slide in effective.roster
                        if slide.get("chart")
                    },
                    evidence_map=revision_evidence,
                    source_fragments=source_fragments,
                    source_manifest_sha256=source_manifest_sha256,
                    effective_spec_revision_id=effective.id,
                    effective_spec_sha256=effective.effective_spec_sha256,
                    spec_lock_sha256=effective.spec_lock_sha256,
                    organization_id=organization_id,
                    created_at=str(snapshot.payload["createdAt"]),
                )
            else:
                whole_rendered = _run_adapter(
                    root,
                    whole_plan,
                    "regeneration-whole-deck",
                    request_id=f"{job_id}-whole-deck-final",
                    organization_id=organization_id,
                    created_at=str(snapshot.payload["createdAt"]),
                )
            svg_path = whole_rendered / "svg_output" / f"slide_{target_index:02d}.svg"
            whole_qa_path = whole_rendered / "qa-report.json"
            whole_qa = json.loads(whole_qa_path.read_text(encoding="utf-8"))
            whole_qa_sha256 = sha256_file(whole_qa_path)
            whole_content_qa_sha256 = canonical_sha256(whole_qa.get("contentQa") or {})
            expected_effective_sha256: str | None = None
            if effective is not None and effective_revision_id is not None:
                instruction_sha256 = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
                preview_compilation = compile_operations(
                    effective_spec_revision_id=effective_revision_id,
                    base_payload=effective.payload,
                    base_effective_spec_sha256=effective.effective_spec_sha256,
                    operations=[
                        {
                            "type": "regenerate",
                            "slideId": target.slide_id,
                            "resultTitle": new_title,
                            "resultBody": new_body,
                            "instructionSha256": instruction_sha256,
                        }
                    ],
                    actor_id=job.created_by,
                )
                expected_effective_payload = {
                    **preview_compilation.payload,
                    "presentationRevisionId": revision_id,
                    "wholeDeckFinalGate": "passed",
                    "wholeDeckFinalQaSha256": whole_qa_sha256,
                    "publicationReady": True,
                }
                expected_effective_sha256 = canonical_sha256(expected_effective_payload)
            artifact_row = _artifact(
                artifact_id=artifact_id,
                organization_id=organization_id,
                artifact_type="presentation_slide_svg",
                path=svg_path,
                media_type="image/svg+xml",
            )
            manifest = {
                "schemaVersion": 1,
                "artifactId": manifest_id,
                "artifactType": "presentation_revision_manifest",
                "organizationId": organization_id,
                "presentationId": job.presentation_id,
                "presentationRevisionId": revision_id,
                "basedOnRevisionId": job.base_revision_id,
                "regenerationJobId": job.id,
                "instructionSha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
                "slideId": job.slide_id,
                "slideArtifactId": artifact_id,
                "slideSha256": artifact_row.sha256,
                "candidateQa": candidate_qa,
                "wholeDeckFinalQa": whole_qa,
                "wholeDeckFinalQaSha256": whole_qa_sha256,
                "contentQaSha256": whole_content_qa_sha256,
                "evidenceMapSha256": (whole_qa.get("bindings") or {}).get(
                    "evidenceMapSha256"
                ),
                "quickGenerate": effective is None,
                "exactRoster": (
                    [slide["pnn"] for slide in effective.roster] if effective else None
                ),
                "effectiveSpecRevisionId": effective_revision_id,
                "effectiveSpecSha256": expected_effective_sha256,
                "contentMode": base.payload.get("contentMode"),
                "engineProfile": base.payload.get("engineProfile"),
                "authoring": base.payload.get("authoring"),
                "authoringMode": base.payload.get("authoringMode"),
                "authoringDisclosure": base.payload.get("authoringDisclosure"),
                "suggestedFilename": base.payload.get("suggestedFilename"),
            }
            manifest_path = root / "presentation-revision-manifest.json"
            _write_json(manifest_path, manifest)
            manifest_row = _artifact(
                artifact_id=manifest_id,
                organization_id=organization_id,
                artifact_type="presentation_revision_manifest",
                path=manifest_path,
                media_type="application/json",
            )
            store.put_file(artifact_row.object_key, svg_path, artifact_row.media_type)
            store.put_file(manifest_row.object_key, manifest_path, manifest_row.media_type)

            with session_factory.begin() as session:
                locked_job = session.scalar(
                    select(SlideRegenerationJob)
                    .where(SlideRegenerationJob.id == job_id)
                    .with_for_update()
                )
                presentation = session.scalar(
                    select(Presentation)
                    .where(Presentation.id == locked_job.presentation_id)
                    .with_for_update()
                )
                if presentation.deleted_at is not None:
                    locked_job.status = "cancelled"
                    locked_job.terminal_at = datetime.now(UTC)
                    return "cancelled"
                if presentation.current_revision_id != locked_job.base_revision_id:
                    locked_job.status = "failed"
                    locked_job.error_code = "base_revision_stale"
                    locked_job.terminal_at = datetime.now(UTC)
                    return "failed"
                base = session.get(PresentationRevision, locked_job.base_revision_id)
                base_effective = _effective_revision(session, base)
                rows = list(
                    session.scalars(
                        select(SlideVersion)
                        .where(SlideVersion.presentation_revision_id == base.id)
                        .order_by(SlideVersion.position)
                    )
                )
                slide_values = [_slide_values(row) for row in rows]
                for slide in slide_values:
                    if slide["slideId"] == locked_job.slide_id:
                        slide.update(
                            {
                                "status": "ready",
                                "title": new_title,
                                "body": new_body,
                                "artifactId": artifact_id,
                                "errorCode": None,
                            }
                        )
                partial = any(slide["status"] == "failed" for slide in slide_values)
                revision_number = (
                    int(
                        session.scalar(
                            select(func.max(PresentationRevision.revision_number)).where(
                                PresentationRevision.presentation_id == presentation.id
                            )
                        )
                        or 0
                    )
                    + 1
                )
                payload = {
                    "schemaVersion": 1,
                    "presentationRevisionId": revision_id,
                    "presentationId": presentation.id,
                    "generationJobId": presentation.generation_job_id,
                    "snapshotId": base.snapshot_id,
                    "revisionNumber": revision_number,
                    "basedOnRevisionId": base.id,
                    "operationSet": [
                        {
                            "type": "regenerate",
                            "slideId": locked_job.slide_id,
                            "instructionSha256": hashlib.sha256(
                                locked_job.instruction.encode("utf-8")
                            ).hexdigest(),
                        }
                    ],
                    "partial": partial,
                    "acceptedMissing": base.accepted_missing,
                    "contentMode": base.payload.get("contentMode"),
                    "engineProfile": base.payload.get("engineProfile"),
                    "authoring": base.payload.get("authoring"),
                    "authoringMode": base.payload.get("authoringMode"),
                    "authoringDisclosure": base.payload.get("authoringDisclosure"),
                    "suggestedFilename": base.payload.get("suggestedFilename"),
                    "slides": [
                        {
                            key: value
                            for key, value in slide.items()
                            if key != "sourceSlideVersionId"
                        }
                        for slide in slide_values
                    ],
                }
                effective_row = None
                if base_effective is not None and effective_revision_id is not None:
                    effective_row = persist_compilation(
                        session,
                        base=base_effective,
                        presentation_revision_id=revision_id,
                        operations=[
                            {
                                "type": "regenerate",
                                "slideId": locked_job.slide_id,
                                "resultTitle": new_title,
                                "resultBody": new_body,
                                "instructionSha256": hashlib.sha256(
                                    locked_job.instruction.encode("utf-8")
                                ).hexdigest(),
                            }
                        ],
                        actor_id=locked_job.created_by,
                        effective_spec_revision_id=effective_revision_id,
                        whole_deck_final_qa_sha256=whole_qa_sha256,
                    )
                    if effective_row.effective_spec_sha256 != expected_effective_sha256:
                        raise RuntimeError("effective spec compilation changed after QA")
                    payload.update(
                        {
                            "effectiveSpecRevisionId": effective_row.id,
                            "effectiveSpecSha256": effective_row.effective_spec_sha256,
                            "contentMode": base.payload.get("contentMode"),
                            "wholeDeckFinalGate": "passed",
                            "wholeDeckFinalQaSha256": whole_qa_sha256,
                        }
                    )
                session.add_all([artifact_row, manifest_row])
                revision = PresentationRevision(
                    id=revision_id,
                    organization_id=organization_id,
                    presentation_id=presentation.id,
                    generation_job_id=presentation.generation_job_id,
                    snapshot_id=base.snapshot_id,
                    manifest_artifact_id=manifest_id,
                    based_on_revision_id=base.id,
                    actor_id=locked_job.created_by,
                    revision_number=revision_number,
                    operation="regenerate_slide",
                    partial=partial,
                    accepted_missing=base.accepted_missing,
                    payload=payload,
                    payload_sha256=canonical_sha256(payload),
                )
                session.add(revision)
                session.flush()
                for slide in slide_values:
                    source_version = slide["sourceSlideVersionId"]
                    slide_payload = {
                        key: value for key, value in slide.items() if key != "sourceSlideVersionId"
                    }
                    session.add(
                        SlideVersion(
                            id=new_ulid(),
                            organization_id=organization_id,
                            presentation_revision_id=revision.id,
                            slide_id=slide["slideId"],
                            outline_slide_id=slide["outlineSlideId"],
                            position=slide["position"],
                            status=slide["status"],
                            title=slide["title"],
                            body=slide["body"],
                            artifact_id=slide["artifactId"],
                            source_slide_version_id=source_version,
                            error_code=slide["errorCode"],
                            payload_sha256=canonical_sha256(slide_payload),
                        )
                    )
                presentation.current_revision_id = revision.id
                presentation.status = "partial" if partial else "ready"
                presentation.lock_version += 1
                locked_job.status = "succeeded"
                locked_job.result_revision_id = revision.id
                locked_job.result_artifact_id = artifact_id
                locked_job.error_code = None
                locked_job.terminal_at = datetime.now(UTC)
                session.add(
                    UsageLedger(
                        id=new_ulid(),
                        organization_id=organization_id,
                        job_id=presentation.generation_job_id,
                        metric="slides",
                        quantity=1,
                        dedupe_key=f"regeneration:{locked_job.id}:slides",
                        details={"regenerationJobId": locked_job.id},
                        occurred_at=datetime.now(UTC),
                    )
                )
        return "succeeded"
    except (AdapterError, OSError, ValueError) as error:
        with session_factory.begin() as session:
            failed = session.get(SlideRegenerationJob, job_id)
            if failed is not None and failed.status == "running":
                failed.status = "failed"
                failed.error_code = f"slide_qa_failed:{error}"[:80]
                failed.terminal_at = datetime.now(UTC)
        return "failed"


def process_export(
    session_factory: sessionmaker[Session],
    job_id: str,
    organization_id: str,
    *,
    object_store: PresentationObjectStore | None = None,
) -> str:
    store = object_store or WorkerObjectStore(WorkerObjectSettings.from_env())
    with session_factory.begin() as session:
        job = session.scalar(
            select(ExportJob)
            .where(ExportJob.id == job_id, ExportJob.organization_id == organization_id)
            .with_for_update()
        )
        if job is None:
            return "noop_missing"
        if job.status in {"succeeded", "failed", "cancelled"}:
            return f"noop_{job.status}"
        presentation = session.get(Presentation, job.presentation_id)
        revision = session.get(PresentationRevision, job.presentation_revision_id)
        if presentation is None or presentation.deleted_at is not None or revision is None:
            job.status = "cancelled"
            job.terminal_at = datetime.now(UTC)
            return "cancelled"
        slides = list(
            session.scalars(
                select(SlideVersion)
                .where(SlideVersion.presentation_revision_id == revision.id)
                .order_by(SlideVersion.position)
            )
        )
        if any(slide.status == "failed" for slide in slides) and not revision.accepted_missing:
            job.status = "failed"
            job.error_code = "missing_slides_not_accepted"
            job.terminal_at = datetime.now(UTC)
            return "failed"
        snapshot = session.get(GenerationSnapshot, revision.snapshot_id)
        if snapshot is None:
            job.status = "failed"
            job.error_code = "snapshot_missing"
            job.terminal_at = datetime.now(UTC)
            return "failed"
        effective = _effective_revision(session, revision)
        if (
            effective is not None
            and effective.payload.get("specLockDisposition") == "derived-pending-gate2"
        ):
            job.status = "failed"
            job.error_code = "spec_lock_gate2_required"
            job.terminal_at = datetime.now(UTC)
            return "failed"
        reusable: dict[str, Any] | None = None
        if (
            effective is not None
            and effective.based_on_id is None
            and effective.payload.get("publicationReady") is True
            and effective.payload.get("wholeDeckFinalGate") == "passed"
        ):
            canonical = effective.payload.get("canonicalArtifacts") or {}
            canonical_pptx_id = canonical.get("pptxArtifactId")
            canonical_pptx = (
                session.scalar(
                    select(Artifact).where(
                        Artifact.id == canonical_pptx_id,
                        Artifact.organization_id == organization_id,
                        Artifact.status == "published",
                    )
                )
                if canonical_pptx_id
                else None
            )
            canonical_gates_present = all(
                canonical.get(key)
                for key in (
                    "finalSvgReportSha256",
                    "packageQaSha256",
                    "evidenceMapSha256",
                    "contentQaSha256",
                )
            )
            if canonical_pptx is not None and canonical_gates_present and (
                not canonical.get("pptxSha256") or canonical["pptxSha256"] == canonical_pptx.sha256
            ):
                reusable = {
                    "artifactId": canonical_pptx.id,
                    "artifactType": canonical_pptx.artifact_type,
                    "objectKey": canonical_pptx.object_key,
                    "sha256": canonical_pptx.sha256,
                    "mimeType": canonical_pptx.media_type,
                    "sizeBytes": canonical_pptx.size_bytes,
                    "effectiveSpecRevisionId": effective.id,
                    "effectiveSpecSha256": effective.effective_spec_sha256,
                    "finalSvgReportSha256": canonical.get("finalSvgReportSha256"),
                    "packageQaSha256": canonical.get("packageQaSha256"),
                    "evidenceMapSha256": canonical.get("evidenceMapSha256"),
                    "contentQaSha256": canonical.get("contentQaSha256"),
                }
        job.status = "running"
        job.stage = "compiling"
        job.attempt += 1
        slide_values = [_slide_values(slide) for slide in slides if slide.status == "ready"]

    artifact_id = _stable_id(f"export:{job_id}:pptx")
    manifest_id = _stable_id(f"export:{job_id}:manifest")
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        with tempfile.TemporaryDirectory(prefix="instant-ppt-export-") as temporary:
            root = Path(temporary)
            if reusable is not None:
                manifest = {
                    "schemaVersion": 1,
                    "exportId": job_id,
                    "presentationRevisionId": revision.id,
                    "artifact": reusable,
                    "reusedFromArtifactId": reusable["artifactId"],
                    "effectiveSpecRevisionId": reusable["effectiveSpecRevisionId"],
                    "effectiveSpecSha256": reusable["effectiveSpecSha256"],
                    "contentMode": revision.payload.get("contentMode"),
                    "authoring": revision.payload.get("authoring"),
                    "authoringMode": revision.payload.get("authoringMode"),
                    "authoringDisclosure": revision.payload.get(
                        "authoringDisclosure"
                    ),
                    "suggestedFilename": revision.payload.get("suggestedFilename"),
                    "requestedFilename": job.options.get("filename"),
                    "evidenceMapSha256": reusable["evidenceMapSha256"],
                    "contentQaSha256": reusable["contentQaSha256"],
                    "compilerVersion": snapshot.engine_version,
                    "engineProfile": revision.payload.get("engineProfile")
                    or "default-agentic",
                    "quickGenerate": False,
                    "renderSkipped": True,
                    "reuseReason": "exact-unedited-canonical-revision",
                    "createdAt": created_at,
                }
                manifest_path = root / "export-manifest.json"
                _write_json(manifest_path, manifest)
                manifest_artifact = _artifact(
                    artifact_id=manifest_id,
                    organization_id=organization_id,
                    artifact_type="export_manifest",
                    path=manifest_path,
                    media_type="application/json",
                )
                store.put_file(
                    manifest_artifact.object_key,
                    manifest_path,
                    manifest_artifact.media_type,
                )
                with session_factory.begin() as session:
                    locked = session.scalar(
                        select(ExportJob).where(ExportJob.id == job_id).with_for_update()
                    )
                    if locked.status != "running":
                        return f"noop_{locked.status}"
                    locked.stage = "publishing"
                    locked.status = "succeeded"
                    locked.artifact_id = reusable["artifactId"]
                    locked.manifest_artifact_id = manifest_id
                    locked.error_code = None
                    locked.terminal_at = datetime.now(UTC)
                    session.add(manifest_artifact)
                    presentation_row = session.get(Presentation, locked.presentation_id)
                    session.add(
                        UsageLedger(
                            id=new_ulid(),
                            organization_id=organization_id,
                            job_id=presentation_row.generation_job_id,
                            metric="exports",
                            quantity=1,
                            dedupe_key=f"export:{locked.id}:exports",
                            details={
                                "presentationRevisionId": locked.presentation_revision_id,
                                "renderSkipped": True,
                            },
                            occurred_at=datetime.now(UTC),
                        )
                    )
                return "succeeded"
            plan = (
                _effective_deck_plan(snapshot, presentation, effective)
                if effective is not None
                else _deck_plan(snapshot, presentation, slide_values)
            )
            if effective is not None:
                rendered = root / "export"
                effective_deck = DeckPlan.model_validate(plan)
                with session_factory() as grounding_session:
                    grounding_effective = grounding_session.get(
                        EffectiveDesignSpecRevision, effective.id
                    )
                    revision_evidence, source_fragments, source_manifest_sha256 = (
                        _revision_evidence(
                            grounding_session,
                            snapshot,
                            grounding_effective,
                            effective_deck,
                            object_store=store,
                            workspace=root / "export-grounding",
                        )
                    )
                render_revision_deck(
                    effective_deck,
                    rendered,
                    chart_specs={
                        str(slide["slideId"]): dict(slide["chart"])
                        for slide in effective.roster
                        if slide.get("chart")
                    },
                    evidence_map=revision_evidence,
                    source_fragments=source_fragments,
                    source_manifest_sha256=source_manifest_sha256,
                    effective_spec_revision_id=effective.id,
                    effective_spec_sha256=effective.effective_spec_sha256,
                    spec_lock_sha256=effective.spec_lock_sha256,
                    organization_id=organization_id,
                    created_at=created_at,
                )
            else:
                rendered = _run_adapter(
                    root,
                    plan,
                    "export",
                    request_id=f"{job_id}-exact-revision",
                    organization_id=organization_id,
                    created_at=created_at,
                )
            pptx_path = rendered / "deck.pptx"
            json.loads(
                (rendered / "validation" / "pptx-package-qa.json").read_text(encoding="utf-8")
            )
            whole_deck_qa_path = rendered / "qa-report.json"
            whole_deck_qa = json.loads(whole_deck_qa_path.read_text(encoding="utf-8"))
            whole_deck_qa_sha256 = sha256_file(whole_deck_qa_path)
            pptx_artifact = _artifact(
                artifact_id=artifact_id,
                organization_id=organization_id,
                artifact_type="export_pptx",
                path=pptx_path,
                media_type=PPTX_MEDIA_TYPE,
            )
            manifest = {
                "schemaVersion": 1,
                "exportId": job_id,
                "presentationRevisionId": revision.id,
                "artifact": {
                    "schemaVersion": 1,
                    "artifactId": artifact_id,
                    "organizationId": organization_id,
                    "artifactType": "export_pptx",
                    "objectKey": pptx_artifact.object_key,
                    "sha256": pptx_artifact.sha256,
                    "mimeType": PPTX_MEDIA_TYPE,
                    "sizeBytes": pptx_artifact.size_bytes,
                    "engineVersion": snapshot.engine_version,
                    "fontPackVersion": snapshot.font_pack_version,
                    "snapshotId": snapshot.id,
                    "presentationRevisionId": revision.id,
                    "createdAt": created_at,
                },
                "reusedFromArtifactId": None,
                "effectiveSpecRevisionId": effective.id if effective else None,
                "effectiveSpecSha256": (effective.effective_spec_sha256 if effective else None),
                "contentMode": revision.payload.get("contentMode"),
                "authoring": revision.payload.get("authoring"),
                "authoringMode": revision.payload.get("authoringMode"),
                "authoringDisclosure": revision.payload.get("authoringDisclosure"),
                "suggestedFilename": revision.payload.get("suggestedFilename"),
                "requestedFilename": job.options.get("filename"),
                "wholeDeckFinalQaSha256": whole_deck_qa_sha256,
                "contentQaSha256": canonical_sha256(
                    whole_deck_qa.get("contentQa") or {}
                ),
                "evidenceMapSha256": (whole_deck_qa.get("bindings") or {}).get(
                    "evidenceMapSha256"
                ),
                "engineProfile": revision.payload.get("engineProfile")
                or (
                    "default-agentic-revision"
                    if effective is not None
                    else "quick-engineering"
                ),
                "quickGenerate": effective is None,
                "exactRoster": (
                    [slide["pnn"] for slide in effective.roster] if effective else None
                ),
                "compilerVersion": snapshot.engine_version,
                "packageQaReportId": manifest_id,
                "createdAt": created_at,
            }
            manifest_path = root / "export-manifest.json"
            _write_json(manifest_path, manifest)
            manifest_artifact = _artifact(
                artifact_id=manifest_id,
                organization_id=organization_id,
                artifact_type="export_manifest",
                path=manifest_path,
                media_type="application/json",
            )
            store.put_file(pptx_artifact.object_key, pptx_path, pptx_artifact.media_type)
            store.put_file(
                manifest_artifact.object_key,
                manifest_path,
                manifest_artifact.media_type,
            )
            with session_factory.begin() as session:
                locked = session.scalar(
                    select(ExportJob).where(ExportJob.id == job_id).with_for_update()
                )
                if locked.status != "running":
                    return f"noop_{locked.status}"
                presentation_row = session.get(Presentation, locked.presentation_id)
                if presentation_row.deleted_at is not None:
                    locked.status = "cancelled"
                    locked.terminal_at = datetime.now(UTC)
                    return "cancelled"
                locked.stage = "package_qa"
                session.add_all([pptx_artifact, manifest_artifact])
                session.flush()
                locked.stage = "publishing"
                locked.status = "succeeded"
                locked.artifact_id = artifact_id
                locked.manifest_artifact_id = manifest_id
                locked.error_code = None
                locked.terminal_at = datetime.now(UTC)
                session.add(
                    UsageLedger(
                        id=new_ulid(),
                        organization_id=organization_id,
                        job_id=presentation_row.generation_job_id,
                        metric="exports",
                        quantity=1,
                        dedupe_key=f"export:{locked.id}:exports",
                        details={"presentationRevisionId": locked.presentation_revision_id},
                        occurred_at=datetime.now(UTC),
                    )
                )
        return "succeeded"
    except (AdapterError, OSError, ValueError) as error:
        with session_factory.begin() as session:
            failed = session.get(ExportJob, job_id)
            if failed is not None and failed.status == "running":
                failed.status = "failed"
                failed.error_code = f"export_package_qa_failed:{error}"[:80]
                failed.terminal_at = datetime.now(UTC)
        return "failed"


def _cleanup_artifact_ids(session: Session, draft: Draft) -> set[str]:
    artifact_ids: set[str] = set()
    presentations = list(
        session.scalars(select(Presentation).where(Presentation.draft_id == draft.id))
    )
    presentation_ids = [row.id for row in presentations]
    if presentation_ids:
        revisions = list(
            session.scalars(
                select(PresentationRevision).where(
                    PresentationRevision.presentation_id.in_(presentation_ids)
                )
            )
        )
        artifact_ids.update(row.manifest_artifact_id for row in revisions)
        revision_ids = [row.id for row in revisions]
        if revision_ids:
            artifact_ids.update(
                value
                for value in session.scalars(
                    select(SlideVersion.artifact_id).where(
                        SlideVersion.presentation_revision_id.in_(revision_ids),
                        SlideVersion.artifact_id.is_not(None),
                    )
                )
                if value
            )
        exports = list(
            session.scalars(
                select(ExportJob).where(ExportJob.presentation_id.in_(presentation_ids))
            )
        )
        artifact_ids.update(row.artifact_id for row in exports if row.artifact_id)
        artifact_ids.update(row.manifest_artifact_id for row in exports if row.manifest_artifact_id)
    job_ids = list(
        session.scalars(
            select(GenerationJob.id)
            .join(GenerationSnapshot, GenerationSnapshot.id == GenerationJob.snapshot_id)
            .where(GenerationSnapshot.draft_id == draft.id)
        )
    )
    if job_ids:
        artifact_ids.update(
            session.scalars(
                select(GenerationArtifact.artifact_id).where(GenerationArtifact.job_id.in_(job_ids))
            )
        )
    artifact_ids.update(
        value
        for value in session.scalars(
            select(DataExport.artifact_id).where(
                DataExport.draft_id == draft.id, DataExport.artifact_id.is_not(None)
            )
        )
        if value
    )
    if draft.source_id:
        other_drafts = int(
            session.scalar(
                select(func.count(Draft.id)).where(
                    Draft.source_id == draft.source_id,
                    Draft.id != draft.id,
                    Draft.deleted_at.is_(None),
                )
            )
            or 0
        )
        if other_drafts == 0:
            source = session.get(Source, draft.source_id)
            if source and source.input_artifact_id:
                artifact_ids.add(source.input_artifact_id)
            artifact_ids.update(
                session.scalars(
                    select(SourceArtifact.artifact_id).where(
                        SourceArtifact.source_id == draft.source_id
                    )
                )
            )
    return artifact_ids


def process_project_cleanup(
    session_factory: sessionmaker[Session],
    job_id: str,
    organization_id: str,
    *,
    object_store: PresentationObjectStore | None = None,
) -> str:
    store = object_store or WorkerObjectStore(WorkerObjectSettings.from_env())
    with session_factory.begin() as session:
        job = session.scalar(
            select(ProjectCleanupJob)
            .where(
                ProjectCleanupJob.id == job_id,
                ProjectCleanupJob.organization_id == organization_id,
            )
            .with_for_update()
        )
        if job is None:
            return "noop_missing"
        if job.status == "succeeded":
            return "noop_succeeded"
        draft = session.get(Draft, job.draft_id)
        if draft is None or draft.deleted_at is None:
            job.status = "failed"
            job.error_code = "draft_not_deleted"
            job.terminal_at = datetime.now(UTC)
            return "failed"
        job.status = "running"
        artifact_ids = _cleanup_artifact_ids(session, draft)
        generation_jobs = list(
            session.scalars(
                select(GenerationJob)
                .join(GenerationSnapshot, GenerationSnapshot.id == GenerationJob.snapshot_id)
                .where(GenerationSnapshot.draft_id == draft.id)
                .with_for_update()
            )
        )
        for generation_job in generation_jobs:
            if generation_job.status in {"queued", "running", "cancel_requested"}:
                generation_job.status = "cancelled"
                generation_job.terminal_at = datetime.now(UTC)
                generation_job.lease_owner = None
                generation_job.lease_expires_at = None
        exports = list(
            session.scalars(
                select(ExportJob)
                .join(Presentation, Presentation.id == ExportJob.presentation_id)
                .where(Presentation.draft_id == draft.id)
                .with_for_update()
            )
        )
        for export in exports:
            if export.status in {"queued", "running"}:
                export.status = "cancelled"
                export.terminal_at = datetime.now(UTC)
        for presentation in session.scalars(
            select(Presentation).where(Presentation.draft_id == draft.id).with_for_update()
        ):
            presentation.deleted_at = draft.deleted_at
        artifacts = list(
            session.scalars(
                select(Artifact).where(
                    Artifact.organization_id == organization_id,
                    Artifact.id.in_(artifact_ids),
                )
            )
        )
        object_keys = [artifact.object_key for artifact in artifacts]

    removed = 0
    failures: list[str] = []
    for object_key in object_keys:
        try:
            store.remove(object_key)
            removed += 1
        except Exception:
            failures.append(object_key)
    with session_factory.begin() as session:
        job = session.scalar(
            select(ProjectCleanupJob).where(ProjectCleanupJob.id == job_id).with_for_update()
        )
        artifacts = list(
            session.scalars(
                select(Artifact).where(
                    Artifact.organization_id == organization_id,
                    Artifact.id.in_(artifact_ids),
                )
            )
        )
        now = datetime.now(UTC)
        failed_keys = set(failures)
        for artifact in artifacts:
            artifact.revoked_at = now
            if artifact.object_key not in failed_keys:
                artifact.status = "deleted"
                artifact.deleted_at = now
            else:
                artifact.status = "revoked"
        job.result = {
            "artifactCount": len(artifacts),
            "removedObjectCount": removed,
            "failedObjectCount": len(failures),
        }
        job.status = "succeeded" if not failures else "failed"
        job.error_code = None if not failures else "object_cleanup_incomplete"
        job.terminal_at = now
    return "succeeded" if not failures else "failed"
