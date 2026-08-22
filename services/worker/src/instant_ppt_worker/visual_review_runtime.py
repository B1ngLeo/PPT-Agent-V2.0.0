"""Hash-bound render and multimodal review loop for Agent-authored slide decks."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageColor, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from instant_ppt_worker.presentation_agent_tools import SceneNode, SlideSceneGraph
from instant_ppt_worker.presentation_blueprint import canonical_sha256
from instant_ppt_worker.providers import ProviderRequestError, TextProvider
from instant_ppt_worker.workflow_models import WorkflowRequestV2


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


class VisualReviewReport(VisualReviewContract):
    schema_version: Literal[1] = 1
    workflow_run_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    review_round: int = Field(ge=1, le=2)
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


class VisualReviewError(RuntimeError):
    pass


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


def _color(value: str, fallback: str = "#000000") -> tuple[int, int, int, int] | None:
    if value == "none":
        return None
    try:
        rgb = ImageColor.getrgb(value)
    except ValueError:
        rgb = ImageColor.getrgb(fallback)
    return (*rgb[:3], 255)


def _draw_node(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    node: SceneNode,
    project: Path,
) -> None:
    box = (node.x, node.y, node.x + node.width, node.y + node.height)
    if node.kind == "group":
        for child in node.children:
            _draw_node(image, draw, child, project)
        return
    if node.kind == "shape":
        fill = _color(node.fill)
        outline = _color(node.stroke)
        width = max(1, round(node.stroke_width)) if outline else 0
        if node.shape == "ellipse":
            draw.ellipse(box, fill=fill, outline=outline, width=width)
        elif node.shape == "line":
            draw.line(box, fill=outline or fill or (0, 0, 0, 255), width=width)
        elif node.shape == "round-rect":
            draw.rounded_rectangle(
                box,
                radius=min(20, node.height / 4),
                fill=fill,
                outline=outline,
                width=width,
            )
        else:
            draw.rectangle(box, fill=fill, outline=outline, width=width)
        return
    if node.kind == "text":
        font = _font(node.font_size, bold=node.font_weight >= 600)
        anchor = {"start": "la", "middle": "ma", "end": "ra"}[node.text_anchor]
        draw.multiline_text(
            (node.x, node.y),
            str(node.text),
            fill=_color(node.text_color) or (0, 0, 0, 255),
            font=font,
            spacing=max(2, round(node.font_size * 0.25)),
            anchor=anchor,
        )
        return
    if node.kind == "image":
        source = (project / "svg_output" / str(node.href)).resolve()
        with Image.open(source) as opened:
            visual = opened.convert("RGBA")
            target = (max(1, round(node.width)), max(1, round(node.height)))
            if node.crop == "contain":
                visual.thumbnail(target, Image.Resampling.LANCZOS)
                offset = (
                    round(node.x + (node.width - visual.width) / 2),
                    round(node.y + (node.height - visual.height) / 2),
                )
            else:
                scale = max(target[0] / visual.width, target[1] / visual.height)
                visual = visual.resize(
                    (math.ceil(visual.width * scale), math.ceil(visual.height * scale)),
                    Image.Resampling.LANCZOS,
                )
                left = max(0, (visual.width - target[0]) // 2)
                top = max(0, (visual.height - target[1]) // 2)
                visual = visual.crop((left, top, left + target[0], top + target[1]))
                offset = (round(node.x), round(node.y))
            image.alpha_composite(visual, offset)
        return
    if node.kind == "chart" and node.chart is not None:
        draw.rounded_rectangle(
            box,
            radius=12,
            fill=_color(node.fill),
            outline=_color(node.stroke),
            width=1,
        )
        values = [point.value for point in node.chart.values]
        maximum = max(1.0, max(values))
        gap = max(1.0, (node.width - 96) / len(values))
        for index, point in enumerate(node.chart.values):
            height = max(1.0, (node.height - 120) * max(0, point.value) / maximum)
            x = node.x + 56 + index * gap + gap * 0.2
            y = node.y + node.height - 64 - height
            draw.rounded_rectangle(
                (x, y, x + gap * 0.6, y + height),
                radius=5,
                fill=_color("#2563EB" if index == 0 else "#0F766E"),
            )
            draw.text(
                (x + gap * 0.3, node.y + node.height - 42),
                point.label,
                font=_font(13),
                fill=_color("#334155"),
                anchor="ma",
            )
        return
    if node.kind == "table" and node.table is not None:
        rows = [node.table.columns, *node.table.rows]
        cell_width = node.width / len(node.table.columns)
        cell_height = node.height / len(rows)
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                cell = (
                    node.x + column_index * cell_width,
                    node.y + row_index * cell_height,
                    node.x + (column_index + 1) * cell_width,
                    node.y + (row_index + 1) * cell_height,
                )
                draw.rectangle(
                    cell,
                    fill=_color("#E2E8F0" if row_index == 0 else "#FFFFFF"),
                    outline=_color("#CBD5E1"),
                    width=1,
                )
                draw.text(
                    (cell[0] + 8, cell[1] + 8),
                    value,
                    font=_font(14, bold=row_index == 0),
                    fill=_color("#1E293B"),
                )


def _render_scene_graph(project: Path, scene_path: Path, target: Path) -> None:
    graph = SlideSceneGraph.model_validate_json(scene_path.read_text(encoding="utf-8"))
    image = Image.new("RGBA", (1280, 720), _color(graph.background) or (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    for node in graph.nodes:
        _draw_node(image, draw, node, project)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(target, format="PNG", optimize=True)


def render_visual_assets(project: Path, *, review_round: int) -> dict[str, Any]:
    preview = project / ".preview" / f"round-{review_round}"
    preview.mkdir(parents=True, exist_ok=True)
    scene_paths = sorted((project / "agent" / "scene-graphs").glob("P*.json"))
    svg_paths = sorted((project / "svg_output").glob("slide_*.svg"))
    if len(scene_paths) != len(svg_paths) or not svg_paths:
        raise VisualReviewError(
            "visual review requires one current Scene Graph for every approved SVG page"
        )
    records: list[dict[str, Any]] = []
    for index, (scene_path, svg_path) in enumerate(
        zip(scene_paths, svg_paths, strict=True), start=1
    ):
        target = preview / f"slide_{index:02d}.png"
        _render_scene_graph(project, scene_path, target)
        records.append(
            {
                "pnn": f"P{index:02d}",
                "svgSha256": _sha_file(svg_path),
                "sceneGraphSha256": _sha_file(scene_path),
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
    schema = VisualReviewReport.model_json_schema(by_alias=True)
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Review the contact sheet and every page image. Return only strict JSON. "
                "Do not edit slides. A successful report has zero blocking issues. "
                f"reviewContext={json.dumps(context, ensure_ascii=False, separators=(',', ':'))}; "
                f"schema={json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}"
            ),
        },
        _review_image_part(project / render_set["contactSheetKey"]),
    ]
    content.extend(
        _review_image_part(project / page["pngKey"]) for page in render_set["pages"]
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are the read-only Visual Review Agent. Inspect rendered pixels against "
                "the supplied rubric. Never author or patch SVG, never invent source facts, and "
                "return only VisualReviewReport v1 JSON."
            ),
        },
        {"role": "user", "content": content},
    ]
    prompt_sha256 = canonical_sha256(messages)
    total_input = 0
    total_output = 0
    elapsed = 0.0
    report: VisualReviewReport | None = None
    completion_model = request.versions.model
    last_error = "invalid visual review output"
    for repair_count in range(max_schema_repairs + 1):
        started = time.monotonic()
        completion = provider.complete(
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "visual_review", "schema": schema},
            },
            max_completion_tokens=request.runtime.max_completion_tokens_per_turn,
        )
        elapsed += max(0.0, time.monotonic() - started)
        total_input += completion.prompt_tokens
        total_output += completion.completion_tokens
        completion_model = completion.model
        try:
            decoded = json.loads(completion.content)
            report = VisualReviewReport.model_validate(decoded)
            if (
                report.workflow_run_id != request.workflow_run_id
                or report.review_round != review_round
                or report.subject_sha256 != subject_sha256
                or report.render_set_sha256 != render_set["renderSetSha256"]
                or report.contact_sheet_sha256 != render_set["contactSheetSha256"]
                or any(issue.pnn not in roster for issue in report.issues if issue.pnn)
            ):
                raise ValueError("visual review ownership/hash/roster does not match the request")
            break
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            last_error = str(error)[:500]
            if repair_count >= max_schema_repairs:
                raise ProviderRequestError(
                    "visual-review-structured-output", None, None
                ) from error
            messages.extend(
                [
                    {"role": "assistant", "content": completion.content},
                    {
                        "role": "user",
                        "content": (
                            "Return only a corrected VisualReviewReport v1 JSON object. "
                            f"Validation error: {last_error}"
                        ),
                    },
                ]
            )
    if report is None:
        raise VisualReviewError(last_error)
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
        "schemaRepairCount": repair_count,
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
