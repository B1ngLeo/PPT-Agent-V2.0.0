"""Hash-bound render and multimodal review loop for Agent-authored slide decks."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import resvg_py
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from instant_ppt_worker.canonical import canonical_sha256
from instant_ppt_worker.providers import TextProvider
from instant_ppt_worker.workflow_models import WorkflowRequestV2

VISUAL_REVIEW_MAX_COMPLETION_TOKENS = 40_000
VISUAL_REVIEW_MAX_PAGES_PER_BATCH = 2
_NOTO_FONT_ROOT = Path("/usr/share/fonts")
_NOTO_SANS_REGULAR = Path(
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
)
_NOTO_SANS_BOLD = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
_NOTO_SERIF_REGULAR = Path(
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
)


def _visual_review_completion_limit(runtime_limit: int) -> int:
    """Keep multimodal review bounded without constraining SVG authoring turns."""

    return min(runtime_limit, VISUAL_REVIEW_MAX_COMPLETION_TOKENS)


def _visual_review_page_batches(
    pages: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Bound each multimodal call while retaining contact-sheet deck context."""

    return [
        pages[index : index + VISUAL_REVIEW_MAX_PAGES_PER_BATCH]
        for index in range(0, len(pages), VISUAL_REVIEW_MAX_PAGES_PER_BATCH)
    ]


class VisualReviewContract(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: (
            value.split("_")[0]
            + "".join(part.title() for part in value.split("_")[1:])
        ),
        populate_by_name=True,
        extra="forbid",
    )


class VisualReviewFinding(VisualReviewContract):
    issue_id: str = Field(pattern=r"^VR\d{2,3}$")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    category: Literal[
        "hierarchy",
        "density-whitespace",
        "alignment-rhythm-balance",
        "consecutive-repetition",
        "content-visual-fit",
        "image-crop-contrast-readability",
        "deck-consistency",
    ]
    severity: Literal["blocking", "advisory"]
    scope: Literal["page", "deck"]
    pnn: str | None = Field(default=None, pattern=r"^P\d{2,3}$")
    owner: Literal["strategist", "executor"]
    message: str = Field(min_length=1, max_length=1000)
    region: str = Field(min_length=1, max_length=300)
    suggested_action: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_scope(self) -> VisualReviewFinding:
        if self.scope == "page" and self.pnn is None:
            raise ValueError("page visual findings require pnn")
        if self.scope == "deck" and self.pnn is not None:
            raise ValueError("deck visual findings cannot claim one pnn")
        return self


class VisualReviewModelFinding(VisualReviewContract):
    """Minimal subjective finding returned by the multimodal model."""

    category: Literal[
        "hierarchy",
        "density-whitespace",
        "alignment-rhythm-balance",
        "consecutive-repetition",
        "content-visual-fit",
        "image-crop-contrast-readability",
        "deck-consistency",
    ]
    severity: Literal["blocking", "advisory"]
    pnn: str | None = Field(default=None, pattern=r"^P\d{2,3}$")
    message: str = Field(min_length=1, max_length=1000)
    region: str = Field(min_length=1, max_length=300)
    suggested_action: str = Field(min_length=1, max_length=1000)


class VisualReviewModelResult(VisualReviewContract):
    """Strict model-facing contract; provenance is attached by the runtime."""

    issues: list[VisualReviewModelFinding] = Field(default_factory=list, max_length=80)


VISUAL_REVIEW_HARD_MAX_ROUNDS = 5
_MATERIAL_ADVISORY_MARKERS = (
    "excessive",
    "unbalanced",
    "inconsistent footer",
    "pagination",
    "page number",
    "disproportionately",
    "truncated",
    "incomplete",
    "clipped",
    "overlap",
    "过多留白",
    "失衡",
    "页脚不一致",
    "页码",
    "截断",
    "重叠",
)


def effective_visual_severity(finding: VisualReviewModelFinding) -> str:
    """Promote delivery-impacting advisories so the adaptive loop repairs them."""

    if finding.severity == "blocking":
        return "blocking"
    message = f"{finding.message} {finding.region} {finding.suggested_action}".casefold()
    if finding.category == "deck-consistency":
        return "blocking"
    if any(marker in message for marker in _MATERIAL_ADVISORY_MARKERS):
        return "blocking"
    return "advisory"


def visual_finding_fingerprint(
    *, category: str, scope: str, pnn: str | None, region: str
) -> str:
    """Return a cross-round identity that ignores mutable reviewer wording."""

    normalized_region = re.sub(r"\s+", " ", region).strip().casefold()
    return canonical_sha256(
        {
            "category": category,
            "scope": scope,
            "pnn": pnn,
            "region": normalized_region,
        }
    )


def visual_review_metrics(
    report: dict[str, Any], roster: Iterable[str]
) -> dict[str, Any]:
    """Build an explainable, lexicographically ordered quality measurement."""

    roster_values = list(roster)
    blocking = [issue for issue in report.get("issues") or [] if issue["severity"] == "blocking"]
    advisory_count = sum(
        1 for issue in report.get("issues") or [] if issue["severity"] == "advisory"
    )
    affected: set[str] = set()
    for issue in blocking:
        if issue.get("scope") == "deck":
            affected.update(roster_values)
        elif issue.get("pnn"):
            affected.add(str(issue["pnn"]))
    quality_key = [len(blocking), len(affected), advisory_count]
    return {
        "blockingCount": quality_key[0],
        "affectedPageCount": quality_key[1],
        "advisoryCount": quality_key[2],
        "score": quality_key[0] * 10_000 + quality_key[1] * 100 + quality_key[2],
        "qualityKey": quality_key,
        "blockingFingerprints": sorted(
            str(issue["fingerprint"]) for issue in blocking if issue.get("fingerprint")
        ),
    }


def adaptive_visual_review_decision(
    *,
    review_round: int,
    max_rounds: int,
    metrics_history: list[dict[str, Any]],
    current_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Choose pass, repair, rollback, or bounded manual handoff from quality progress."""

    if not 1 <= max_rounds <= VISUAL_REVIEW_HARD_MAX_ROUNDS:
        raise ValueError("visual review max rounds must be between one and five")
    all_metrics = [*metrics_history, current_metrics]
    best_index = min(
        range(len(all_metrics)), key=lambda index: tuple(all_metrics[index]["qualityKey"])
    )
    best_round = best_index + 1
    if current_metrics["blockingCount"] == 0:
        return {
            "decision": "pass",
            "reason": "zero-blocking",
            "bestRound": best_round,
            "stagnationCount": 0,
        }
    if review_round >= max_rounds:
        return {
            "decision": "needs-manual",
            "reason": "max-rounds",
            "bestRound": best_round,
            "stagnationCount": 0,
        }
    if metrics_history:
        best_previous_key = min(
            tuple(item["qualityKey"]) for item in metrics_history
        )
        current_key = tuple(current_metrics["qualityKey"])
        if current_key > best_previous_key:
            return {
                "decision": "rollback-needs-manual",
                "reason": "quality-regressed",
                "bestRound": best_round,
                "stagnationCount": 1,
            }
        stagnation_count = 0
        for index in range(len(all_metrics) - 1, 0, -1):
            if tuple(all_metrics[index]["qualityKey"]) < tuple(
                all_metrics[index - 1]["qualityKey"]
            ):
                break
            stagnation_count += 1
        if stagnation_count >= 2:
            return {
                "decision": "needs-manual",
                "reason": "stalled-two-rounds",
                "bestRound": best_round,
                "stagnationCount": stagnation_count,
            }
    else:
        stagnation_count = 0
    return {
        "decision": "repair",
        "reason": "blocking-with-progress-budget",
        "bestRound": best_round,
        "stagnationCount": stagnation_count,
    }


class VisualReviewReport(VisualReviewContract):
    schema_version: Literal[1] = 1
    workflow_run_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    review_round: int = Field(ge=1, le=VISUAL_REVIEW_HARD_MAX_ROUNDS)
    subject_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    render_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    contact_sheet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    passed: bool
    issues: list[VisualReviewFinding] = Field(default_factory=list, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_result(self) -> VisualReviewReport:
        identifiers = [finding.issue_id for finding in self.issues]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("visual review issue IDs must be unique")
        blocking = any(finding.severity == "blocking" for finding in self.issues)
        if self.passed == blocking:
            raise ValueError("visual review passed must mean zero blocking findings")
        return self


def _materialize_batch_report(
    model_result: VisualReviewModelResult,
    *,
    context: dict[str, Any],
    batch_roster: list[str],
) -> VisualReviewReport:
    """Attach deterministic IDs, ownership, provenance, and pass/fail state."""

    findings: list[dict[str, Any]] = []
    for index, finding in enumerate(model_result.issues, start=1):
        scope = "deck" if finding.pnn is None else "page"
        fingerprint = visual_finding_fingerprint(
            category=finding.category,
            scope=scope,
            pnn=finding.pnn,
            region=finding.region,
        )
        findings.append(
            {
                "issueId": f"VR{index:03d}",
                "fingerprint": fingerprint,
                "category": finding.category,
                "severity": effective_visual_severity(finding),
                "scope": scope,
                "pnn": finding.pnn,
                "owner": "strategist" if scope == "deck" else "executor",
                "message": finding.message,
                "region": finding.region,
                "suggestedAction": finding.suggested_action,
            }
        )
    blocking = any(finding["severity"] == "blocking" for finding in findings)
    summary = (
        f"Detected {len(findings)} visual finding(s) in batch "
        f"{', '.join(batch_roster)}."
        if findings
        else f"No visual findings detected in batch {', '.join(batch_roster)}."
    )
    return VisualReviewReport.model_validate(
        {
            "schemaVersion": 1,
            "workflowRunId": context["workflowRunId"],
            "reviewRound": context["reviewRound"],
            "subjectSha256": context["subjectSha256"],
            "renderSetSha256": context["renderSetSha256"],
            "contactSheetSha256": context["contactSheetSha256"],
            "passed": not blocking,
            "issues": findings,
            "summary": summary,
        }
    )


class VisualReviewError(RuntimeError):
    pass


def _merge_visual_review_reports(
    reports: list[VisualReviewReport],
    *,
    context: dict[str, Any],
) -> VisualReviewReport:
    """Merge batch reports into one hash-bound deck report with stable issue IDs."""

    unique_findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for report in reports:
        for finding in report.issues:
            payload = finding.model_dump(by_alias=True, mode="json")
            identity = finding.fingerprint
            if identity in seen:
                continue
            seen.add(identity)
            unique_findings.append(payload)
    if len(unique_findings) > 80:
        raise VisualReviewError("batched visual review returned more than 80 unique issues")
    for index, finding in enumerate(unique_findings, start=1):
        finding["issueId"] = f"VR{index:03d}"
    blocking = any(
        finding["severity"] == "blocking" for finding in unique_findings
    )
    summary = " | ".join(
        f"Batch {index}: {report.summary}"
        for index, report in enumerate(reports, start=1)
    )[:2000]
    return VisualReviewReport.model_validate(
        {
            "schemaVersion": 1,
            "workflowRunId": context["workflowRunId"],
            "reviewRound": context["reviewRound"],
            "subjectSha256": context["subjectSha256"],
            "renderSetSha256": context["renderSetSha256"],
            "contactSheetSha256": context["contactSheetSha256"],
            "passed": not blocking,
            "issues": unique_findings,
            "summary": summary or "Batched visual review completed.",
        }
    )


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font_candidates(*, bold: bool) -> tuple[Path, ...]:
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return tuple(
        Path(value)
        for value in (
            windows / ("msyhbd.ttc" if bold else "msyh.ttc"),
            windows / ("arialbd.ttf" if bold else "arial.ttf"),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
    )


def _font(size: float, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    pixel_size = max(8, round(size))
    for path in _font_candidates(bold=bold):
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), pixel_size)
        except OSError:
            continue
    return ImageFont.load_default(size=pixel_size)


def _render_svg(svg_path: Path, target: Path) -> None:
    """Rasterize the final SVG, which is the visual-review source of truth."""

    target.parent.mkdir(parents=True, exist_ok=True)
    font_options: dict[str, Any] = {}
    noto_files = [
        path
        for path in (_NOTO_SANS_REGULAR, _NOTO_SANS_BOLD, _NOTO_SERIF_REGULAR)
        if path.is_file()
    ]
    if noto_files:
        # Authored SVGs intentionally use a portable stack such as
        # ``Microsoft YaHei, Arial, sans-serif``.  resvg does not reliably
        # advance from missing named families to its generic Linux fallback,
        # so explicitly bind the generic families to the CJK pack installed in
        # the worker image.  Without this, review PNGs contain the layout
        # geometry but silently lose every text node.
        font_options = {
            "font_dirs": [str(_NOTO_FONT_ROOT)],
            "font_files": [str(path) for path in noto_files],
            "sans_serif_family": "Noto Sans CJK SC",
            "serif_family": "Noto Serif CJK SC",
        }
    try:
        target.write_bytes(
            resvg_py.svg_to_bytes(
                svg_path=str(svg_path),
                resources_dir=str(svg_path.parent),
                width=1280,
                height=720,
                background="#FFFFFF",
                **font_options,
            )
        )
    except Exception as error:  # resvg exposes backend-specific exception types.
        raise VisualReviewError(f"unable to render {svg_path.name}: {error}") from error


def render_visual_assets(project: Path, *, review_round: int) -> dict[str, Any]:
    preview = project / ".preview" / f"round-{review_round}"
    preview.mkdir(parents=True, exist_ok=True)
    svg_paths = sorted((project / "svg_output").glob("slide_*.svg"))
    if not svg_paths:
        raise VisualReviewError("visual review requires at least one approved SVG page")
    records: list[dict[str, Any]] = []
    for index, svg_path in enumerate(svg_paths, start=1):
        pnn = f"P{index:02d}"
        target = preview / f"slide_{index:02d}.png"
        _render_svg(svg_path, target)
        records.append(
            {
                "pnn": pnn,
                "svgSha256": _sha_file(svg_path),
                "authoringMode": "validated-direct-svg",
                "pngKey": target.relative_to(project).as_posix(),
                "pngSha256": _sha_file(target),
                "bytes": target.stat().st_size,
                "width": 1280,
                "height": 720,
            }
        )
    contact = _contact_sheet(project, records, preview / "contact-sheet.png")
    render_set_sha256 = canonical_sha256(records)
    payload = {
        "schema": "instant-ppt.visual-render-set.v1",
        "reviewRound": review_round,
        "renderSetSha256": render_set_sha256,
        "contactSheetKey": contact.relative_to(project).as_posix(),
        "contactSheetSha256": _sha_file(contact),
        "pages": records,
    }
    payload["receiptSha256"] = canonical_sha256(payload)
    path = project / "validation" / f"visual-render-round-{review_round}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return payload


def _contact_sheet(project: Path, records: list[dict[str, Any]], target: Path) -> Path:
    columns = min(4, max(1, len(records)))
    rows = math.ceil(len(records) / columns)
    tile_width, tile_height, label_height = 320, 180, 30
    sheet = Image.new(
        "RGB",
        (columns * tile_width, rows * (tile_height + label_height)),
        "#0F172A",
    )
    draw = ImageDraw.Draw(sheet)
    for index, record in enumerate(records):
        column, row = index % columns, index // columns
        x, y = column * tile_width, row * (tile_height + label_height)
        with Image.open(project / record["pngKey"]) as opened:
            thumbnail = opened.convert("RGB").resize(
                (tile_width, tile_height), Image.Resampling.LANCZOS
            )
            sheet.paste(thumbnail, (x, y))
        draw.text(
            (x + 10, y + tile_height + 5),
            record["pnn"],
            font=_font(15, bold=True),
            fill="#F8FAFC",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, format="PNG", optimize=True)
    return target


def _review_image_part(path: Path) -> dict[str, Any]:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        image.thumbnail((960, 540), Image.Resampling.LANCZOS)
        stream = io.BytesIO()
        image.save(stream, format="JPEG", quality=78, optimize=True)
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
    }


def _cost(tokens: int, rate: int) -> int:
    return (tokens * rate + 999) // 1000 if tokens and rate else 0


def review_visual_assets(
    provider: TextProvider,
    request: WorkflowRequestV2,
    project: Path,
    *,
    review_round: int,
    subject_sha256: str,
    render_set: dict[str, Any],
    max_schema_repairs: int = 2,
) -> dict[str, Any]:
    if not 0 <= max_schema_repairs <= 2:
        raise ValueError("visual reviewer repairs must be between 0 and 2")
    roster = [page["pnn"] for page in render_set["pages"]]
    context = {
        "workflowRunId": request.workflow_run_id,
        "reviewRound": review_round,
        "subjectSha256": subject_sha256,
        "renderSetSha256": render_set["renderSetSha256"],
        "contactSheetSha256": render_set["contactSheetSha256"],
        "roster": roster,
        "rubric": [
            "hierarchy",
            "density-whitespace",
            "alignment-rhythm-balance",
            "consecutive-repetition",
            "content-visual-fit",
            "image-crop-contrast-readability",
            "deck-consistency",
        ],
    }
    schema = VisualReviewModelResult.model_json_schema(by_alias=True)
    schema_json = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    page_batches = _visual_review_page_batches(list(render_set["pages"]))
    if not page_batches:
        raise VisualReviewError("visual review requires at least one rendered page")
    batch_prompt_sha256s: list[str] = []
    batch_report_payloads: list[dict[str, Any]] = []
    batch_reports: list[VisualReviewReport] = []
    total_input = 0
    total_output = 0
    elapsed = 0.0
    completion_model = request.versions.model
    schema_repair_count = 0
    for batch_index, batch_pages in enumerate(page_batches, start=1):
        batch_roster = [page["pnn"] for page in batch_pages]
        batch_context = {
            "batchIndex": batch_index,
            "batchCount": len(page_batches),
            "batchRoster": batch_roster,
            "deckRoster": roster,
            "rubric": context["rubric"],
        }
        batch_context_json = json.dumps(
            batch_context, ensure_ascii=False, separators=(",", ":")
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Use the contact sheet for deck-wide context and inspect every supplied "
                    "batch page image in detail. Return only strict JSON. Do not edit slides. "
                    "Set pnn to one of batchRoster for page findings and to null only for "
                    "deck-wide findings. Return an empty issues array when no issue is visible. "
                    "Treat material delivery defects as blocking, including excessive or "
                    "unbalanced whitespace, clipped/overlapping text, unreadable hierarchy, "
                    "inconsistent footers or pagination, and incomplete audience-facing copy. "
                    f"reviewContext={batch_context_json}; schema={schema_json}"
                ),
            },
            _review_image_part(project / render_set["contactSheetKey"]),
        ]
        content.extend(
            _review_image_part(project / page["pngKey"]) for page in batch_pages
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are the read-only Visual Review Agent. Inspect rendered pixels against "
                    "the supplied rubric. Never author or patch SVG, never invent source facts, "
                    "and return only VisualReviewModelResult v1 JSON."
                ),
            },
            {"role": "user", "content": content},
        ]
        batch_prompt_sha256s.append(canonical_sha256(messages))
        batch_model_result: VisualReviewModelResult | None = None
        last_error = "invalid visual review output"
        for repair_count in range(max_schema_repairs + 1):
            started = time.monotonic()
            completion = provider.complete(
                messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "visual_review",
                        "schema": schema,
                        "strict": True,
                    },
                },
                max_completion_tokens=_visual_review_completion_limit(
                    request.runtime.max_completion_tokens_per_turn
                ),
            )
            elapsed += max(0.0, time.monotonic() - started)
            total_input += completion.prompt_tokens
            total_output += completion.completion_tokens
            completion_model = completion.model
            try:
                decoded = json.loads(completion.content)
                batch_model_result = VisualReviewModelResult.model_validate(decoded)
                if any(
                    issue.pnn not in batch_roster
                    for issue in batch_model_result.issues
                    if issue.pnn
                ):
                    raise ValueError("visual review page finding is outside batchRoster")
                break
            except (json.JSONDecodeError, ValidationError, ValueError) as error:
                last_error = str(error)[:500]
                if repair_count >= max_schema_repairs:
                    raise VisualReviewError(
                        f"visual review structured output remained invalid: {last_error}"
                    ) from error
                messages.extend(
                    [
                        {"role": "assistant", "content": completion.content},
                        {
                            "role": "user",
                            "content": (
                                "Return only a corrected VisualReviewModelResult v1 JSON object. "
                                f"Validation error: {last_error}"
                            ),
                        },
                    ]
                )
        if batch_model_result is None:
            raise VisualReviewError(last_error)
        schema_repair_count += repair_count
        batch_report = _materialize_batch_report(
            batch_model_result,
            context=context,
            batch_roster=batch_roster,
        )
        batch_reports.append(batch_report)
        batch_report_payloads.append(
            batch_model_result.model_dump(by_alias=True, mode="json")
        )
    report = _merge_visual_review_reports(batch_reports, context=context)
    prompt_sha256 = canonical_sha256(batch_prompt_sha256s)
    usage = {
        "inputTokens": total_input,
        "outputTokens": total_output,
        "costMicrounits": _cost(
            total_input, request.runtime.input_cost_microunits_per_1k
        )
        + _cost(total_output, request.runtime.output_cost_microunits_per_1k),
        "elapsedSeconds": elapsed,
    }
    report_payload = report.model_dump(by_alias=True, mode="json")
    evidence = {
        "schema": "instant-ppt.visual-review-evidence.v1",
        "workflowRunId": request.workflow_run_id,
        "reviewRound": review_round,
        "subjectSha256": subject_sha256,
        "promptSha256": prompt_sha256,
        "provider": provider.provider_name,
        "providerModel": completion_model,
        "modelVersion": request.versions.model,
        "promptVersion": request.versions.prompt,
        "referenceVersion": request.versions.reference,
        "schemaRepairCount": schema_repair_count,
        "batchCount": len(page_batches),
        "maxPagesPerBatch": VISUAL_REVIEW_MAX_PAGES_PER_BATCH,
        "batchPromptSha256s": batch_prompt_sha256s,
        "batchReports": batch_report_payloads,
        "usage": usage,
        "report": report_payload,
    }
    evidence["evidenceSha256"] = canonical_sha256(evidence)
    evidence_path = project / "agent" / "visual-reviews" / f"round-{review_round}.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return {
        "structuredReport": report_payload,
        "providerUsage": usage,
        "evidenceSha256": evidence["evidenceSha256"],
        "evidenceKey": evidence_path.relative_to(project).as_posix(),
    }


def blocking_pages(
    report: dict[str, Any], roster: Iterable[str]
) -> dict[str, list[dict[str, Any]]]:
    roster_values = list(roster)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for issue in report.get("issues") or []:
        if issue.get("severity") != "blocking":
            continue
        targets = roster_values if issue.get("scope") == "deck" else [str(issue["pnn"])]
        for pnn in targets:
            grouped.setdefault(pnn, []).append(issue)
    return grouped
