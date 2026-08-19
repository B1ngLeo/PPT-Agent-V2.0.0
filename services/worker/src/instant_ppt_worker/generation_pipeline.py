"""Durable G06 generation pipeline from an approved snapshot to immutable artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from instant_ppt_domain.artifacts import tenant_object_key
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
    Presentation,
    ProviderCall,
    SlideVersion,
)
from instant_ppt_domain.service import (
    SlideStart,
    canonical_sha256,
    claim_job,
    complete_slide,
    heartbeat_job,
    set_job_stage,
    set_slide_stage,
    start_next_slide,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_worker.adapter import execute
from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.errors import AdapterError
from instant_ppt_worker.models import DeckPlan, RenderDeckRequest
from instant_ppt_worker.providers import (
    ImageProvider,
    OpenAIImageProvider,
    ProviderConfigurationError,
    ProviderRequestError,
)
from instant_ppt_worker.renderer import render_slide_candidate
from instant_ppt_worker.settings import OpenAIImageSettings
from instant_ppt_worker.source_parser import deterministic_ulid
from instant_ppt_worker.source_pipeline import WorkerObjectSettings, WorkerObjectStore


class GenerationObjectStore(Protocol):
    def put_file(self, object_key: str, path: Path, media_type: str) -> None: ...


class InjectedGenerationCrash(RuntimeError):
    """Test-only abrupt boundary used by process-kill recovery verification."""


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


def _load_generation(
    session: Session, job_id: str, organization_id: str
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


def _reused_slide_artifacts(
    session: Session, job_id: str, organization_id: str
) -> list[dict[str, Any]]:
    presentation = session.scalar(
        select(Presentation).where(
            Presentation.generation_job_id == job_id,
            Presentation.organization_id == organization_id,
        )
    )
    if presentation is None or not presentation.current_revision_id:
        return []
    rows = list(
        session.execute(
            select(SlideVersion, Artifact)
            .join(Artifact, Artifact.id == SlideVersion.artifact_id)
            .where(
                SlideVersion.presentation_revision_id == presentation.current_revision_id,
                SlideVersion.organization_id == organization_id,
                SlideVersion.status == "ready",
                SlideVersion.artifact_id.is_not(None),
            )
            .order_by(SlideVersion.position)
        )
    )
    return [
        {
            "artifactId": artifact.id,
            "artifactType": "generation_slide_svg",
            "objectKey": artifact.object_key,
            "sha256": artifact.sha256,
            "mediaType": artifact.media_type,
            "sizeBytes": artifact.size_bytes,
            "slideId": slide.slide_id,
            "reused": True,
        }
        for slide, artifact in rows
    ]


def _template_binding(snapshot: GenerationSnapshot) -> dict[str, Any]:
    template = dict(
        snapshot.payload.get("templateCandidate") or snapshot.payload["template"]
    )
    roles = ["cover", "content", "ending"]
    return {
        "schemaVersion": 1,
        "templateId": template["templateId"],
        "templateVersionId": snapshot.template_version_id,
        "compatibilityVersion": template["engineCompatibility"],
        "roleBindings": {role: f"layout-{role}" for role in roles},
    }


def _slide_payload(slide: GenerationJobSlide, *, order: int, failed_slot: bool) -> dict[str, Any]:
    role = "content"
    if slide.position == 1:
        role = "cover"
    title = slide.title or "未命名页面"
    body = list(slide.body) or ["内容待补充"]
    if failed_slot:
        title = f"{title}（生成失败）"
        body = ["该页面生成失败，可在任务监控中重试；稳定 slideId 已保留。"]
    elif role == "cover" and len(body) > 1:
        body = ["；".join(body)]
    return {
        "schemaVersion": 1,
        "slideId": slide.slide_id,
        "outlineSlideId": slide.outline_slide_id or slide.slide_id,
        "order": order,
        "role": role,
        "title": title,
        "body": body,
        "editable": True,
    }


def _deck_plan(
    snapshot: GenerationSnapshot,
    slides: list[GenerationJobSlide],
    *,
    candidate: GenerationJobSlide | None = None,
) -> dict[str, Any]:
    selected = [candidate] if candidate is not None else slides
    intent = dict(snapshot.payload.get("intent", {}))
    title = str(intent.get("title") or intent.get("topic") or "AI 演示文稿")
    return {
        "schemaVersion": 1,
        "snapshotId": snapshot.id,
        "title": title,
        "modeId": "native",
        "templateBinding": _template_binding(snapshot),
        "slides": [
            _slide_payload(
                slide,
                order=index,
                failed_slot=candidate is None and slide.status == "failed",
            )
            for index, slide in enumerate(selected)
        ],
    }


def _run_adapter(
    root: Path,
    deck_plan: dict[str, Any],
    output_key: str,
    *,
    request_id: str,
    organization_id: str,
    created_at: str,
    cover_image_path: Path | None = None,
) -> Path:
    deck_key = f"requests/{request_id}.json"
    _write_canonical(root / deck_key, deck_plan)
    execute(
        RenderDeckRequest(
            schema_version=1,
            request_id=request_id,
            operation="renderDeck",
            workspace_root=str(root),
            deck_plan_key=deck_key,
            cover_image_key=(
                cover_image_path.relative_to(root).as_posix() if cover_image_path else None
            ),
            output_key=output_key,
            organization_id=organization_id,
            created_at=created_at,
        )
    )
    return root / output_key


def _normalize_workspace_paths(item: Any, workspace: str) -> Any:
    if isinstance(item, dict):
        return {key: _normalize_workspace_paths(nested, workspace) for key, nested in item.items()}
    if isinstance(item, list):
        return [_normalize_workspace_paths(nested, workspace) for nested in item]
    if isinstance(item, str):
        return item.replace(workspace, "$WORKSPACE").replace(
            workspace.replace("\\", "/"), "$WORKSPACE"
        )
    return item


def _deterministic_bundle(
    output_dir: Path,
    deck_plan_path: Path,
    target: Path,
    *,
    extra_files: tuple[Path, ...] = (),
) -> None:
    members = [deck_plan_path]
    members.extend(sorted((output_dir / "svg_output").glob("*.svg")))
    members.extend(
        [
            output_dir / "validation" / "svg_quality_report.json",
            output_dir / "validation" / "pptx-package-qa.json",
        ]
    )
    members.extend([output_dir / "qa-report.json", output_dir / "artifact-manifest.json"])
    members.extend(extra_files)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in members:
            if not source.is_file():
                continue
            if source == deck_plan_path:
                relative = "deck-plan.json"
            elif source in extra_files:
                relative = f"images/{source.name}"
            else:
                relative = source.relative_to(output_dir).as_posix()
            info = zipfile.ZipInfo(relative, (2026, 8, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            payload = source.read_bytes()
            if source.suffix.lower() == ".json":
                value = json.loads(payload.decode("utf-8"))
                workspace = str(output_dir.parent.resolve())
                payload = _canonical_bytes(_normalize_workspace_paths(value, workspace))
            archive.writestr(info, payload)


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


def _publish_files(
    store: GenerationObjectStore,
    specs_and_paths: list[tuple[PublishedArtifactSpec, Path]],
) -> None:
    for spec, path in specs_and_paths:
        store.put_file(spec.object_key, path, spec.media_type)


def _cover_image_prompt(snapshot: GenerationSnapshot) -> str:
    intent = dict(snapshot.payload.get("intent") or {})
    outline = dict(snapshot.payload.get("outline") or {})
    title = str(intent.get("title") or intent.get("topic") or "business presentation")[:200]
    story = str(outline.get("storySummary") or intent.get("goal") or "")[:500]
    return (
        "Create a polished 3:2 landscape editorial hero illustration for a professional "
        f"presentation about: {title}. Narrative direction: {story}. Use a restrained modern "
        "business visual language, strong focal composition, generous negative space, realistic "
        "lighting, and no visible text, letters, numbers, logos, watermarks, UI, or brand marks."
    )


def _record_image_provider_call(
    session_factory: sessionmaker[Session],
    snapshot: GenerationSnapshot,
    *,
    provider: str,
    model: str,
    prompt: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    error_code: str | None = None,
) -> None:
    call_id = _stable_id(f"{snapshot.id}:cover-image:{canonical_sha256({'prompt': prompt})}")
    with session_factory.begin() as session:
        if session.get(ProviderCall, call_id) is not None:
            return
        session.add(
            ProviderCall(
                id=call_id,
                organization_id=snapshot.organization_id,
                draft_id=snapshot.draft_id,
                provider=provider,
                model=model,
                purpose="cover_image_generate",
                request_hash=canonical_sha256(
                    {"snapshotId": snapshot.id, "purpose": "cover_image", "prompt": prompt}
                ),
                status=status,
                input_tokens=0,
                output_tokens=0,
                repair_count=0,
                error_code=error_code,
                started_at=started_at,
                finished_at=finished_at,
            )
        )


def _generate_cover_image(
    root: Path,
    session_factory: sessionmaker[Session],
    snapshot: GenerationSnapshot,
    *,
    job_id: str,
    publication_version: int,
    settings: OpenAIImageSettings,
    provider: ImageProvider | None,
) -> tuple[Path | None, str | None, dict[str, Any]]:
    if not settings.enabled or settings.max_images_per_deck == 0:
        return None, None, {"status": "disabled", "maxImagesPerDeck": settings.max_images_per_deck}
    prompt = _cover_image_prompt(snapshot)
    prompt_sha = canonical_sha256({"prompt": prompt})
    started_at = datetime.now(UTC)
    owned_provider = provider is None
    selected = provider
    try:
        if selected is None:
            selected = OpenAIImageProvider(settings)
        image = selected.generate(
            prompt,
            size=settings.size,
            quality=settings.quality,
            idempotency_key=f"cover-{job_id}-v{publication_version}",
        )
        suffixes = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        suffix = suffixes.get(image.media_type)
        if suffix is None:
            raise ProviderRequestError("openai-image", None, None)
        path = root / "images" / f"generated-cover{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image.content)
        finished_at = datetime.now(UTC)
        _record_image_provider_call(
            session_factory,
            snapshot,
            provider=selected.provider_name,
            model=image.model,
            prompt=prompt,
            status="succeeded",
            started_at=started_at,
            finished_at=finished_at,
        )
        return path, image.media_type, {
            "status": "succeeded",
            "provider": selected.provider_name,
            "model": image.model,
            "promptSha256": prompt_sha,
            "size": settings.size,
            "quality": settings.quality,
            "imageCount": 1,
            "maxImagesPerDeck": settings.max_images_per_deck,
        }
    except (ProviderConfigurationError, ProviderRequestError) as error:
        finished_at = datetime.now(UTC)
        provider_name = getattr(selected, "provider_name", "openai-image")
        error_code = (
            "provider_configuration_failed"
            if isinstance(error, ProviderConfigurationError)
            else "provider_request_failed"
        )
        _record_image_provider_call(
            session_factory,
            snapshot,
            provider=provider_name,
            model=settings.model,
            prompt=prompt,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            error_code=error_code,
        )
        return None, None, {
            "status": "failed",
            "provider": provider_name,
            "model": settings.model,
            "promptSha256": prompt_sha,
            "errorCode": error_code,
            "imageCount": 0,
            "maxImagesPerDeck": settings.max_images_per_deck,
        }
    finally:
        if owned_provider and selected is not None:
            close = getattr(selected, "close", None)
            if callable(close):
                close()


def _snapshot_image_settings(
    snapshot: GenerationSnapshot,
    supplied: OpenAIImageSettings | None,
) -> OpenAIImageSettings:
    if supplied is not None:
        return supplied
    settings = OpenAIImageSettings.from_env()
    # The runtime switch is a fail-closed operational kill switch. A previously
    # approved snapshot may narrow image use, but it cannot re-enable calls after
    # the current deployment has disabled the provider.
    if not settings.enabled or settings.max_images_per_deck == 0:
        return replace(settings, enabled=False, max_images_per_deck=0)
    configuration = dict(snapshot.payload.get("providerConfiguration") or {})
    image = dict(configuration.get("image") or {})
    if not image:
        return settings
    return replace(
        settings,
        enabled=bool(image.get("enabled", False)),
        backend=str(image.get("backend") or settings.backend),
        base_url=str(image.get("baseUrl") or settings.base_url),
        model=str(image.get("model") or settings.model),
        output_format=str(image.get("outputFormat") or settings.output_format),
        size=str(image.get("size") or settings.size),
        quality=str(image.get("quality") or settings.quality),
        max_images_per_deck=int(
            image.get("maxImagesPerDeck", settings.max_images_per_deck)
        ),
    )


def process_generation_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    worker_id: str,
    *,
    organization_id: str,
    lease_seconds: int = 30,
    object_store: GenerationObjectStore | None = None,
    image_settings: OpenAIImageSettings | None = None,
    image_provider: ImageProvider | None = None,
    crash_callback: Callable[[SlideStart], None] | None = None,
    before_publish_callback: Callable[[], None] | None = None,
) -> str:
    """Run resumable slide boundaries and one atomic immutable publication."""

    started = time.monotonic()
    store = object_store or WorkerObjectStore(WorkerObjectSettings.from_env())
    with session_factory.begin() as session:
        claimed = claim_job(session, job_id, worker_id, lease_seconds=lease_seconds)
        if claimed is None:
            return "noop_terminal"

    with session_factory() as session:
        claimed_job, claimed_snapshot, claimed_slides = _load_generation(
            session,
            job_id,
            organization_id,
        )
    has_engineering_behavior = bool(
        claimed_job.test_behavior.get("crashOnceAtPosition") is not None
        or int(claimed_job.test_behavior.get("stepDelayMs") or 0) > 0
    )
    is_default = (
        claimed_snapshot.payload.get("engineProfile") == "default-agentic"
        and not has_engineering_behavior
        and all(slide.failure_mode == "none" for slide in claimed_slides)
    )
    if is_default:
        from instant_ppt_worker.default_generation_pipeline import (
            process_default_generation_job,
        )

        return process_default_generation_job(
            session_factory,
            job_id,
            worker_id,
            organization_id=organization_id,
            lease_seconds=lease_seconds,
            object_store=store,
            started=started,
            before_publish_callback=before_publish_callback,
        )

    with tempfile.TemporaryDirectory(prefix="instant-ppt-generation-") as temporary:
        root = Path(temporary)
        while True:
            with session_factory.begin() as session:
                heartbeat_job(session, job_id, worker_id, lease_seconds=lease_seconds)
                slide_start = start_next_slide(session, job_id, worker_id)
                _, snapshot, slides = _load_generation(session, job_id, organization_id)
            if slide_start is None:
                break
            if slide_start.crash_now:
                if crash_callback is not None:
                    crash_callback(slide_start)
                raise InjectedGenerationCrash(
                    f"crash after persisted slide start at position {slide_start.position}"
                )
            if slide_start.step_delay_ms:
                time.sleep(slide_start.step_delay_ms / 1000)
            current = next(item for item in slides if item.slide_id == slide_start.slide_id)
            forced_failure = slide_start.failure_mode == "always" or (
                slide_start.failure_mode == "once" and slide_start.attempt == 1
            )
            if forced_failure:
                with session_factory.begin() as session:
                    complete_slide(
                        session,
                        job_id,
                        slide_start.slide_id,
                        worker_id,
                        succeeded=False,
                        error_code="injected_slide_failure",
                    )
                continue
            try:
                with session_factory.begin() as session:
                    set_slide_stage(session, job_id, slide_start.slide_id, worker_id, "rendering")
                candidate_plan = DeckPlan.model_validate(
                    _deck_plan(snapshot, slides, candidate=current)
                )
                candidate_dir = (
                    root / f"candidates/{current.slide_id}/attempt-{slide_start.attempt}"
                )
                candidate_result = render_slide_candidate(
                    candidate_plan,
                    candidate_dir,
                    visual_index=current.position - 1,
                )
                candidate_svg = candidate_result["svg"]
                candidate_qa = json.loads(candidate_result["qa"].read_text(encoding="utf-8"))
                candidate_qa = _normalize_workspace_paths(candidate_qa, str(root.resolve()))
                with session_factory.begin() as session:
                    set_slide_stage(session, job_id, current.slide_id, worker_id, "qa")
                    complete_slide(
                        session,
                        job_id,
                        current.slide_id,
                        worker_id,
                        succeeded=True,
                        artifact_ref=f"workspace://{current.slide_id}/candidate.svg",
                        render_sha256=sha256_file(candidate_svg),
                        qa_report={"candidate": candidate_qa},
                    )
            except AdapterError as error:
                with session_factory.begin() as session:
                    complete_slide(
                        session,
                        job_id,
                        current.slide_id,
                        worker_id,
                        succeeded=False,
                        error_code=error.code,
                        qa_report={
                            "passed": False,
                            "errorCode": error.code,
                            "detail": error.message[-1000:],
                        },
                    )

        with session_factory() as session:
            job, snapshot, slides = _load_generation(session, job_id, organization_id)
        worker_seconds = max(1, math.ceil(time.monotonic() - started))
        if job.status == "cancel_requested":
            with session_factory.begin() as session:
                cancel_generation_job(
                    session,
                    job_id=job_id,
                    organization_id=organization_id,
                    worker_id=worker_id,
                    worker_seconds=worker_seconds,
                )
            return "cancelled"
        if not any(slide.status == "ready" for slide in slides):
            with session_factory.begin() as session:
                fail_generation_job(
                    session,
                    job_id=job_id,
                    organization_id=organization_id,
                    worker_id=worker_id,
                    error_code="all_slides_failed",
                    worker_seconds=worker_seconds,
                )
            return "failed"
        publication_version = job.publication_version + 1

        with session_factory.begin() as session:
            set_job_stage(session, job_id, worker_id, "deck_qa")
            set_job_stage(session, job_id, worker_id, "compiling")
            heartbeat_job(session, job_id, worker_id, lease_seconds=lease_seconds)
        cover_image_path, cover_media_type, image_generation = _generate_cover_image(
            root,
            session_factory,
            snapshot,
            job_id=job_id,
            publication_version=publication_version,
            settings=_snapshot_image_settings(snapshot, image_settings),
            provider=image_provider,
        )
        plan = _deck_plan(snapshot, slides)
        final_plan_path = root / "deck-plan.json"
        _write_canonical(final_plan_path, plan)
        try:
            final_dir = _run_adapter(
                root,
                plan,
                "final",
                request_id=f"{job_id}-publication",
                organization_id=organization_id,
                created_at=str(snapshot.payload["createdAt"]),
                cover_image_path=cover_image_path,
            )
        except AdapterError as error:
            with session_factory.begin() as session:
                current, _, _ = _load_generation(session, job_id, organization_id)
                if current.status == "cancel_requested":
                    cancel_generation_job(
                        session,
                        job_id=job_id,
                        organization_id=organization_id,
                        worker_id=worker_id,
                        worker_seconds=worker_seconds,
                    )
                    return "cancelled"
                fail_generation_job(
                    session,
                    job_id=job_id,
                    organization_id=organization_id,
                    worker_id=worker_id,
                    error_code=error.code,
                    worker_seconds=worker_seconds,
                )
            return "failed"
        final_qa = json.loads((final_dir / "qa-report.json").read_text(encoding="utf-8"))
        final_qa["reportId"] = _stable_id(f"{job_id}:v{publication_version}:qa-report")
        _write_canonical(final_dir / "qa-report.json", final_qa)
        compiled: dict[str, tuple[str, dict[str, Any]]] = {}
        for index, slide in enumerate(slides, start=1):
            if slide.status != "ready":
                continue
            svg_path = final_dir / "svg_output" / f"slide_{index:02d}.svg"
            compiled[slide.slide_id] = (
                sha256_file(svg_path),
                {"candidate": slide.qa_report.get("candidate", {}), "deck": final_qa},
            )
        with session_factory.begin() as session:
            set_job_stage(session, job_id, worker_id, "package_qa")
            record_compiled_slides(
                session,
                job_id=job_id,
                organization_id=organization_id,
                worker_id=worker_id,
                compiled=compiled,
            )
            heartbeat_job(session, job_id, worker_id, lease_seconds=lease_seconds)

        with session_factory() as session:
            reused_artifacts = _reused_slide_artifacts(session, job_id, organization_id)
        reused_artifacts = [
            item
            for item in reused_artifacts
            if str(item["slideId"]) in compiled
            and compiled[str(item["slideId"])][0] == item["sha256"]
        ]
        reused_slide_ids = {str(item["slideId"]) for item in reused_artifacts}
        presentation_id = _stable_id(f"{job_id}:presentation")
        presentation_revision_id = _stable_id(
            f"{job_id}:presentation-revision:{publication_version}"
        )
        source_bundle = root / "generation-source-bundle.zip"
        _deterministic_bundle(
            final_dir,
            final_plan_path,
            source_bundle,
            extra_files=((cover_image_path,) if cover_image_path else ()),
        )
        specs_and_paths: list[tuple[PublishedArtifactSpec, Path]] = []
        specs_and_paths.extend(
            [
                (
                    _artifact_spec(
                        job_id=job_id,
                        organization_id=organization_id,
                        publication_version=publication_version,
                        kind="generation_source_bundle",
                        path=source_bundle,
                        media_type="application/zip",
                    ),
                    source_bundle,
                ),
                (
                    _artifact_spec(
                        job_id=job_id,
                        organization_id=organization_id,
                        publication_version=publication_version,
                        kind="generation_baseline_pptx",
                        path=final_dir / "deck.pptx",
                        media_type=(
                            "application/vnd.openxmlformats-officedocument."
                            "presentationml.presentation"
                        ),
                    ),
                    final_dir / "deck.pptx",
                ),
                (
                    _artifact_spec(
                        job_id=job_id,
                        organization_id=organization_id,
                        publication_version=publication_version,
                        kind="generation_preview_svg",
                        path=final_dir / "preview.svg",
                        media_type="image/svg+xml",
                    ),
                    final_dir / "preview.svg",
                ),
                (
                    _artifact_spec(
                        job_id=job_id,
                        organization_id=organization_id,
                        publication_version=publication_version,
                        kind="generation_qa_report",
                        path=final_dir / "qa-report.json",
                        media_type="application/json",
                    ),
                    final_dir / "qa-report.json",
                ),
            ]
        )
        if cover_image_path is not None and cover_media_type is not None:
            specs_and_paths.append(
                (
                    _artifact_spec(
                        job_id=job_id,
                        organization_id=organization_id,
                        publication_version=publication_version,
                        kind="generation_ai_cover_image",
                        path=cover_image_path,
                        media_type=cover_media_type,
                    ),
                    cover_image_path,
                )
            )
        for index, slide in enumerate(slides, start=1):
            if slide.status != "ready" or slide.slide_id in reused_slide_ids:
                continue
            path = final_dir / "svg_output" / f"slide_{index:02d}.svg"
            specs_and_paths.append(
                (
                    _artifact_spec(
                        job_id=job_id,
                        organization_id=organization_id,
                        publication_version=publication_version,
                        kind="generation_slide_svg",
                        path=path,
                        media_type="image/svg+xml",
                        slide_id=slide.slide_id,
                    ),
                    path,
                )
            )
        manifest_artifact_id = _stable_id(
            f"{job_id}:v{publication_version}:generation_manifest:deck"
        )
        manifest_object_key = tenant_object_key(organization_id, "published", manifest_artifact_id)
        manifest_payload = {
            "schemaVersion": 1,
            "artifactId": manifest_artifact_id,
            "artifactType": "generation_manifest",
            "organizationId": organization_id,
            "objectKey": manifest_object_key,
            "jobId": job_id,
            "snapshotId": snapshot.id,
            "snapshotSha256": snapshot.snapshot_sha256,
            "publicationVersion": publication_version,
            "presentationId": presentation_id,
            "presentationRevisionId": presentation_revision_id,
            "modeId": snapshot.mode_id,
            "versions": {
                "prompt": snapshot.prompt_version,
                "engine": snapshot.engine_version,
                "container": snapshot.container_version,
                "fontPack": snapshot.font_pack_version,
                "providerConfig": snapshot.provider_config_version,
                "templateVersionId": snapshot.template_version_id,
            },
            "readySlideIds": [slide.slide_id for slide in slides if slide.status == "ready"],
            "failedSlideIds": [slide.slide_id for slide in slides if slide.status == "failed"],
            "imageGeneration": image_generation,
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
            "reusedArtifacts": reused_artifacts,
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
        _publish_files(store, specs_and_paths)
        if before_publish_callback is not None:
            before_publish_callback()
        try:
            with session_factory.begin() as session:
                set_job_stage(session, job_id, worker_id, "publishing")
                publish_generation_result(
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
        except GenerationCancellationObserved:
            with session_factory.begin() as session:
                cancel_generation_job(
                    session,
                    job_id=job_id,
                    organization_id=organization_id,
                    worker_id=worker_id,
                    worker_seconds=worker_seconds,
                )
            return "cancelled"
    return (
        "succeeded" if all(slide.status == "ready" for slide in slides) else "partially_succeeded"
    )
