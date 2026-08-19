"""Strategist-owned image resource preparation for the Default workflow."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from instant_ppt_domain.service import canonical_sha256

from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.errors import RENDER_FAILED, AdapterError
from instant_ppt_worker.paths import ENGINE_SCRIPTS, resolve_key
from instant_ppt_worker.providers import (
    ImageProvider,
    OpenAIImageProvider,
    ProviderConfigurationError,
    ProviderRequestError,
)
from instant_ppt_worker.settings import OpenAIImageSettings
from instant_ppt_worker.workflow_models import WorkflowRequestV2


@dataclass(frozen=True, slots=True)
class ImagePreparation:
    resources: tuple[dict[str, Any], ...]
    by_slide: dict[str, Path]
    native_fallback_slides: frozenset[str]
    blocking_resources: tuple[dict[str, Any], ...]
    inventory_sha256: str
    analysis_sha256: str
    analysis_path: Path
    audit_path: Path


def empty_image_preparation(project: Path) -> ImagePreparation:
    return ImagePreparation(
        resources=(),
        by_slide={},
        native_fallback_slides=frozenset(),
        blocking_resources=(),
        inventory_sha256=canonical_sha256([]),
        analysis_sha256=canonical_sha256([]),
        analysis_path=project / "analysis" / "image_analysis.csv",
        audit_path=project / "analysis" / "image-resource-audit.json",
    )


def _inventory(images_dir: Path) -> str:
    values = [
        {
            "filename": path.name,
            "sha256": sha256_file(path),
            "sizeBytes": path.stat().st_size,
        }
        for path in sorted(images_dir.iterdir())
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    return canonical_sha256(values)


def current_image_inventory_sha256(project: Path) -> str:
    return _inventory(project / "images")


def analyze_image_inventory(project: Path) -> tuple[Path, str, str]:
    """Regenerate image_analysis.csv and bind it to the current live image pool."""

    images_dir = project / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    inventory_sha256 = _inventory(images_dir)
    completed = subprocess.run(
        [sys.executable, str(ENGINE_SCRIPTS / "analyze_images.py"), str(images_dir)],
        cwd=project,
        env={
            **{
                key: value
                for key, value in os.environ.items()
                if key
                in {
                    "PATH",
                    "PATHEXT",
                    "SYSTEMROOT",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "USERPROFILE",
                    "HOMEDRIVE",
                    "HOMEPATH",
                }
            },
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise AdapterError(
            RENDER_FAILED,
            (completed.stderr or completed.stdout or "image analysis failed")[-2000:],
        )
    analysis_path = project / "analysis" / "image_analysis.csv"
    if not analysis_path.is_file():
        raise AdapterError(RENDER_FAILED, "image analyzer returned without its CSV")
    return analysis_path, inventory_sha256, sha256_file(analysis_path)


def _analysis_by_filename(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {str(row["Filename"]): row for row in csv.DictReader(stream)}


def _safe_prompt(request: WorkflowRequestV2, slide_id: str, note: str) -> str:
    slide = next(value for value in request.outline if value.slide_id == slide_id)
    return (
        "Create one restrained editorial illustration for a professional presentation. "
        f"The page role is {slide.role}; its communication intent is: {note}. "
        "Use the deck's navy, blue, teal, and light-neutral visual family, with one clear "
        "focal subject and enough calm space for separately editable SVG copy. The bitmap "
        "must contain no visible text, letters, numbers, logos, watermarks, fake UI, data "
        "labels, or brand marks; all factual evidence and authoritative wording remain native "
        "editable presentation objects."
    )


def _generated_suffix(media_type: str) -> str:
    try:
        return {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }[media_type]
    except KeyError as error:
        raise ProviderRequestError("image-resource", None, None) from error


def _failure_code(error: Exception) -> str:
    if isinstance(error, ProviderConfigurationError):
        return "provider_configuration_failed"
    if isinstance(error, ProviderRequestError):
        return "provider_request_failed"
    return "provider_unavailable"


def prepare_image_resources(
    workspace_root: Path,
    project: Path,
    request: WorkflowRequestV2,
    *,
    api_provider: ImageProvider | None = None,
    host_native_provider: ImageProvider | None = None,
    image_settings: OpenAIImageSettings | None = None,
) -> ImagePreparation:
    """Materialize confirmed assets, refresh facts, and resolve bounded recovery."""

    images_dir = project / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    slide_ids = [value.slide_id for value in request.outline]
    slide_id_set = set(slide_ids)
    first_slide_id = slide_ids[0]
    notes = {
        (first_slide_id if key == "cover" else key): value
        for key, value in request.image.notes.items()
    }
    if any(key not in slide_id_set for key in notes):
        raise AdapterError(RENDER_FAILED, "imageNotes contains a slide outside the exact roster")
    if request.image.scope == "cover_only" and set(notes) != {first_slide_id}:
        raise AdapterError(RENDER_FAILED, "cover_only image scope must bind only P01")
    if request.image.scope == "selective" and not notes:
        raise AdapterError(RENDER_FAILED, "selective image scope requires selected slide roles")

    resources: list[dict[str, Any]] = []
    by_slide: dict[str, Path] = {}
    for descriptor in request.image.provided_assets:
        if any(slide_id not in notes for slide_id in descriptor.slide_ids):
            raise AdapterError(
                RENDER_FAILED,
                "provided image targets must be present in confirmed imageNotes",
            )
        source = resolve_key(workspace_root, descriptor.workspace_key, must_exist=True)
        expected_suffixes = {
            "image/png": {".png"},
            "image/jpeg": {".jpg", ".jpeg"},
            "image/webp": {".webp"},
        }[descriptor.media_type]
        if Path(descriptor.filename).suffix.lower() not in expected_suffixes:
            raise AdapterError(RENDER_FAILED, "provided image filename/mediaType mismatch")
        if not source.is_file() or sha256_file(source) != descriptor.sha256:
            raise AdapterError(RENDER_FAILED, "provided image bytes changed after confirmation")
        destination = images_dir / descriptor.filename
        if destination.exists():
            raise AdapterError(RENDER_FAILED, "image resource filenames must be unique")
        shutil.copyfile(source, destination)
        for slide_id in descriptor.slide_ids:
            if slide_id in by_slide:
                raise AdapterError(
                    RENDER_FAILED,
                    "the current release gate supports one placed image per slide",
                )
            by_slide[slide_id] = destination
        resources.append(
            {
                "assetId": descriptor.asset_id,
                "filename": descriptor.filename,
                "purpose": descriptor.purpose,
                "slideIds": descriptor.slide_ids,
                "required": descriptor.required,
                "cropPolicy": descriptor.crop_policy,
                "layoutPattern": descriptor.layout_pattern,
                "acquireVia": "user",
                "status": "Existing",
                "sha256": descriptor.sha256,
                "mediaType": descriptor.media_type,
                "license": descriptor.license,
            }
        )

    native_fallbacks = {
        value.slide_id: value for value in request.image.office_native_fallbacks
    }
    resolved_native_slides: set[str] = set()
    ai_targets = sorted(notes) if "ai" in request.image.usage else []
    prompts: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    settings = image_settings or OpenAIImageSettings.from_env()
    owned_api_provider: ImageProvider | None = None
    api_configuration_error: Exception | None = None
    if "api" in request.image.ai_path_chain and api_provider is None:
        try:
            if not settings.enabled or settings.max_images_per_deck == 0:
                raise ProviderConfigurationError(
                    "image API requires an explicit request and an enabled reserved quota"
                )
            owned_api_provider = OpenAIImageProvider(settings)
            api_provider = owned_api_provider
        except ProviderConfigurationError as error:
            api_configuration_error = error

    generated_count = 0
    try:
        for slide_id in ai_targets:
            if slide_id in by_slide:
                continue
            slide = next(value for value in request.outline if value.slide_id == slide_id)
            if slide.role not in {"cover", "section", "content", "ending"}:
                raise AdapterError(
                    RENDER_FAILED,
                    "AI images cannot represent data, comparison, timeline, or risk evidence",
                )
            prompt = _safe_prompt(request, slide_id, notes[slide_id])
            prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            attempts: list[dict[str, Any]] = []
            generated = None
            selected_strategy: str | None = None
            strategies = list(request.image.ai_path_chain)
            if settings.max_images_per_deck > 0 and (
                generated_count >= settings.max_images_per_deck
            ):
                attempts.append(
                    {
                        "strategy": strategies[0],
                        "attempt": 0,
                        "status": "failed",
                        "errorCode": "image_quota_exhausted",
                    }
                )
                strategies = []
            for strategy in strategies:
                if strategy == "manual":
                    attempts.append(
                        {
                            "strategy": strategy,
                            "attempt": 1,
                            "status": "needs-manual",
                            "errorCode": "manual_acquisition_required",
                        }
                    )
                    break
                provider = api_provider if strategy == "api" else host_native_provider
                attempt_limit = request.runtime.max_stage_attempts
                for attempt in range(1, attempt_limit + 1):
                    if provider is None:
                        error = (
                            api_configuration_error
                            if strategy == "api" and api_configuration_error is not None
                            else ProviderConfigurationError(
                                f"{strategy} image executor is unavailable"
                            )
                        )
                        attempts.append(
                            {
                                "strategy": strategy,
                                "attempt": attempt,
                                "status": "failed",
                                "errorCode": _failure_code(error),
                            }
                        )
                        continue
                    try:
                        generated = provider.generate(
                            prompt,
                            size=settings.size,
                            quality=settings.quality,
                            idempotency_key=(
                                f"{request.workflow_run_id}-{slide_id}-{strategy}-{attempt}"
                            ),
                        )
                    except (ProviderConfigurationError, ProviderRequestError) as error:
                        attempts.append(
                            {
                                "strategy": strategy,
                                "attempt": attempt,
                                "status": "failed",
                                "errorCode": _failure_code(error),
                            }
                        )
                        continue
                    attempts.append(
                        {
                            "strategy": strategy,
                            "attempt": attempt,
                            "status": "succeeded",
                            "provider": provider.provider_name,
                            "model": generated.model,
                        }
                    )
                    selected_strategy = strategy
                    break
                if generated is not None:
                    break

            filename = f"ai-{slide_id[-8:].lower()}.png"
            if generated is not None and selected_strategy is not None:
                if settings.max_images_per_deck > 0 and (
                    generated_count >= settings.max_images_per_deck
                ):
                    generated = None
                    attempts.append(
                        {
                            "strategy": selected_strategy,
                            "attempt": len(attempts) + 1,
                            "status": "failed",
                            "errorCode": "image_quota_exhausted",
                        }
                    )
                else:
                    suffix = _generated_suffix(generated.media_type)
                    filename = f"ai-{slide_id[-8:].lower()}{suffix}"
                    destination = images_dir / filename
                    destination.write_bytes(generated.content)
                    by_slide[slide_id] = destination
                    generated_count += 1
                    resources.append(
                        {
                            "assetId": None,
                            "filename": filename,
                            "purpose": notes[slide_id],
                            "slideIds": [slide_id],
                            "required": True,
                            "cropPolicy": "adaptive",
                            "layoutPattern": (
                                "#P1-01" if slide_id == first_slide_id else "#P1-02"
                            ),
                            "acquireVia": "ai",
                            "status": "Generated",
                            "sha256": sha256_file(destination),
                            "mediaType": generated.media_type,
                            "license": "provider-generated",
                            "provider": (
                                api_provider.provider_name
                                if selected_strategy == "api" and api_provider is not None
                                else host_native_provider.provider_name
                                if host_native_provider is not None
                                else selected_strategy
                            ),
                            "model": generated.model,
                            "prompt": prompt,
                            "promptSha256": prompt_sha256,
                            "selectedPath": request.image.ai_path,
                            "declaredPathChain": request.image.ai_path_chain,
                            "selectedStrategy": selected_strategy,
                            "attempts": attempts,
                            "costMicrounits": settings.cost_microunits_per_image,
                        }
                    )
                    prompts.append(
                        {
                            "id": f"image-{slide_id}",
                            "filename": filename,
                            "prompt": prompt,
                            "promptSha256": prompt_sha256,
                            "pageRole": (
                                "hero_page" if slide_id == first_slide_id else "local"
                            ),
                            "textPolicy": "none",
                            "status": "Generated",
                            "selectedPath": request.image.ai_path,
                            "declaredPathChain": request.image.ai_path_chain,
                            "selectedStrategy": selected_strategy,
                            "provider": resources[-1]["provider"],
                            "model": generated.model,
                            "attempts": attempts,
                        }
                    )

            fallback = native_fallbacks.get(slide_id)
            last_automated_attempt = next(
                (
                    value
                    for value in reversed(attempts)
                    if value.get("strategy") != "manual"
                ),
                None,
            )
            last_error_code = str(
                last_automated_attempt.get("errorCode", "acquisition_exhausted")
                if last_automated_attempt
                else "manual_acquisition_required"
            )
            fallback_approved = fallback is not None and (
                last_error_code in fallback.trigger_codes
                or "acquisition_exhausted" in fallback.trigger_codes
            )
            if generated is None and fallback_approved and fallback is not None:
                resolved_native_slides.add(slide_id)
                resources.append(
                    {
                        "assetId": None,
                        "filename": None,
                        "purpose": notes[slide_id],
                        "slideIds": [slide_id],
                        "required": True,
                        "acquireVia": "ai",
                        "realizationVia": "office-native",
                        "status": "Resolved-Native",
                        "construction": fallback.construction,
                        "triggerCodes": fallback.trigger_codes,
                        "appliedTriggerCode": last_error_code,
                        "decisionReceiptSha256": fallback.decision_receipt_sha256,
                        "prompt": prompt,
                        "promptSha256": prompt_sha256,
                        "attempts": attempts,
                        "costMicrounits": 0,
                    }
                )
                prompts.append(
                    {
                        "id": f"image-{slide_id}",
                        "filename": None,
                        "prompt": prompt,
                        "promptSha256": prompt_sha256,
                        "pageRole": (
                            "hero_page" if slide_id == first_slide_id else "local"
                        ),
                        "textPolicy": "none",
                        "status": "Resolved-Native",
                        "selectedPath": request.image.ai_path,
                        "declaredPathChain": request.image.ai_path_chain,
                        "construction": fallback.construction,
                        "decisionReceiptSha256": fallback.decision_receipt_sha256,
                        "attempts": attempts,
                    }
                )
                continue
            if generated is not None:
                continue
            item = {
                "id": f"image-{slide_id}",
                "filename": filename,
                "prompt": prompt,
                "promptSha256": prompt_sha256,
                "pageRole": "hero_page" if slide_id == first_slide_id else "local",
                "textPolicy": "none",
                "status": "Needs-Manual",
                "selectedPath": request.image.ai_path,
                "declaredPathChain": request.image.ai_path_chain,
                "attempts": attempts,
                "lastErrorCode": last_error_code,
            }
            prompts.append(item)
            row = {
                "assetId": None,
                "filename": filename,
                "purpose": notes[slide_id],
                "slideIds": [slide_id],
                "required": True,
                "cropPolicy": "adaptive",
                "layoutPattern": "#P1-01" if slide_id == first_slide_id else "#P1-02",
                "acquireVia": "ai",
                "status": "Needs-Manual",
                "prompt": prompt,
                "promptSha256": prompt_sha256,
                "selectedPath": request.image.ai_path,
                "declaredPathChain": request.image.ai_path_chain,
                "attempts": attempts,
                "costMicrounits": 0,
            }
            resources.append(row)
            blocking.append(row)
    finally:
        if owned_api_provider is not None:
            close = getattr(owned_api_provider, "close", None)
            if callable(close):
                close()

    planned_slide_ids = {
        str(slide_id)
        for resource in resources
        for slide_id in resource.get("slideIds", [])
    }
    for slide_id in sorted(set(notes) - planned_slide_ids):
        acquire_via = next(
            (
                value
                for value in request.image.usage
                if value in {"web", "provided", "placeholder"}
            ),
            "manual",
        )
        row = {
            "assetId": None,
            "filename": f"manual-{slide_id[-8:].lower()}.png",
            "purpose": notes[slide_id],
            "slideIds": [slide_id],
            "required": True,
            "cropPolicy": "adaptive",
            "layoutPattern": "#P1-01" if slide_id == first_slide_id else "#P1-02",
            "acquireVia": acquire_via,
            "status": "Needs-Manual",
            "failureCode": "declared_image_source_unavailable",
            "license": "unresolved",
            "costMicrounits": 0,
        }
        resources.append(row)
        blocking.append(row)
    if prompts:
        manifest = {
            "schema_version": 1,
            "deck_rendering": "custom-editorial-data-journalism",
            "color_scheme": {
                "background": "#F8FAFC",
                "primary": "#0F172A",
                "accent": "#2563EB",
                "secondary_accent": "#0F766E",
            },
            "items": prompts,
        }
        prompt_path = images_dir / "image_prompts.json"
        prompt_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    analysis_path, inventory_sha256, analysis_sha256 = analyze_image_inventory(project)
    facts = _analysis_by_filename(analysis_path)
    for resource in resources:
        filename = resource.get("filename")
        if resource["status"] not in {"Existing", "Generated", "Sourced"} or not filename:
            continue
        fact = facts.get(str(filename))
        if fact is None:
            raise AdapterError(RENDER_FAILED, "provided image is absent from fresh analysis")
        resource.update(
            {
                "dimensions": f"{fact['Width']}x{fact['Height']}",
                "ratio": fact["AspectRatio"],
                "analysisSha256": analysis_sha256,
            }
        )
    audit = {
        "schemaVersion": 1,
        "imageScope": request.image.scope,
        "imageUsage": request.image.usage,
        "imageNotes": notes,
        "inventorySha256": inventory_sha256,
        "analysisSha256": analysis_sha256,
        "fresh": True,
        "resources": resources,
        "requiredCount": sum(bool(value.get("required")) for value in resources),
        "blockingCount": len(blocking),
        "generatedCount": generated_count,
        "costMicrounits": sum(int(value.get("costMicrounits", 0)) for value in resources),
    }
    audit["auditSha256"] = canonical_sha256(audit)
    audit_path = project / "analysis" / "image-resource-audit.json"
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return ImagePreparation(
        resources=tuple(resources),
        by_slide=by_slide,
        native_fallback_slides=frozenset(resolved_native_slides),
        blocking_resources=tuple(blocking),
        inventory_sha256=inventory_sha256,
        analysis_sha256=analysis_sha256,
        analysis_path=analysis_path,
        audit_path=audit_path,
    )
