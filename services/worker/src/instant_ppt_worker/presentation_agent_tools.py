"""Constrained semantic authoring tools for the Main Presentation Agent.

The registry deliberately exposes page/domain operations instead of shell,
network, database, or general filesystem access.  Every mutation is scoped to
the current run and page and emits hash-bound evidence plus stale propagation.
"""

from __future__ import annotations

import html
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from defusedxml import ElementTree as DefusedET
from pydantic import BaseModel, ConfigDict, Field, model_validator

from instant_ppt_worker.presentation_blueprint import canonical_sha256
from instant_ppt_worker.workflow_models import PageBlueprintArtifact, WorkflowRequestV2

AGENT_TOOL_NAMES = (
    "read_approved_context",
    "write_planning_artifact",
    "read_design_catalog",
    "write_or_patch_slide_svg",
    "run_svg_gate",
    "render_slide_or_deck",
    "run_chart_gate",
    "request_visual_review",
    "complete_or_pause_stage",
)

MUTATING_TOOLS = frozenset({"write_planning_artifact", "write_or_patch_slide_svg"})
WRITE_STALE_TARGETS = (
    "final-svg-gate",
    "chart-gate",
    "final-svg-content-gate",
    "step7-finalize",
    "step7-export",
    "postflight",
    "pptx-content-gate",
    "publication",
)

_TOOL_ID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_PNN = re.compile(r"^P\d{2,3}$")
_NODE_ID = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
_PLANNING_NAME = re.compile(r"^[a-z][a-z0-9-]{1,63}\.json$")
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_SVG_ALLOWED_TAGS = frozenset(
    {
        "svg",
        "g",
        "defs",
        "linearGradient",
        "radialGradient",
        "stop",
        "clipPath",
        "rect",
        "circle",
        "ellipse",
        "line",
        "path",
        "polyline",
        "polygon",
        "text",
        "tspan",
        "image",
        "metadata",
    }
)
_SVG_FORBIDDEN_TEXT = re.compile(
    r"(?:<!DOCTYPE|<!ENTITY|<script\b|<foreignObject\b|javascript:)",
    re.IGNORECASE,
)


class ToolPolicyError(ValueError):
    """Raised when an Agent asks for a capability outside its scoped policy."""


class SceneContract(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: (
            value.split("_")[0]
            + "".join(part.title() for part in value.split("_")[1:])
        ),
        populate_by_name=True,
        extra="forbid",
    )


class SceneChartPoint(SceneContract):
    label: str = Field(min_length=1, max_length=160)
    value: float


class SceneChart(SceneContract):
    object_key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,79}$")
    chart_type: Literal["bar", "column", "line", "area", "scatter"]
    values: list[SceneChartPoint] = Field(min_length=2, max_length=16)
    unit: str = Field(min_length=1, max_length=40)
    source_text: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_values(self) -> SceneChart:
        labels = [point.label.casefold() for point in self.values]
        if len(labels) != len(set(labels)):
            raise ValueError("chart labels must be unique")
        return self


class SceneTable(SceneContract):
    object_key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,79}$")
    columns: list[str] = Field(min_length=1, max_length=12)
    rows: list[list[str]] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_grid(self) -> SceneTable:
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("table rows must match the exact column grid")
        return self


class SceneNode(SceneContract):
    node_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,79}$")
    kind: Literal["text", "shape", "group", "image", "chart", "table"]
    x: float = Field(ge=0, le=1280)
    y: float = Field(ge=0, le=720)
    width: float = Field(gt=0, le=1280)
    height: float = Field(gt=0, le=720)
    text: str | None = Field(default=None, max_length=8000)
    shape: Literal["rect", "round-rect", "ellipse", "line"] | None = None
    fill: str = "#FFFFFF"
    stroke: str = "#CBD5E1"
    stroke_width: float = Field(default=1, ge=0, le=20)
    font_family: str = Field(default="Microsoft YaHei, Arial, sans-serif", max_length=160)
    font_size: float = Field(default=22, ge=8, le=96)
    font_weight: Literal[400, 500, 600, 700] = 400
    text_color: str = "#1E293B"
    text_anchor: Literal["start", "middle", "end"] = "start"
    href: str | None = Field(default=None, max_length=260)
    crop: Literal["contain", "cover"] = "cover"
    children: list[SceneNode] = Field(default_factory=list, max_length=80)
    chart: SceneChart | None = None
    table: SceneTable | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> SceneNode:
        if self.x + self.width > 1280.001 or self.y + self.height > 720.001:
            raise ValueError("scene node must remain inside the 1280x720 canvas")
        for color in (self.fill, self.stroke, self.text_color):
            if color != "none" and _HEX_COLOR.fullmatch(color) is None:
                raise ValueError("scene colors must be six-digit hex or none")
        if self.kind == "text" and not self.text:
            raise ValueError("text nodes require text")
        if self.kind == "shape" and self.shape is None:
            raise ValueError("shape nodes require a supported shape")
        if self.kind == "group" and not self.children:
            raise ValueError("group nodes require children")
        if self.kind != "group" and self.children:
            raise ValueError("only group nodes may contain children")
        if self.kind == "image" and self.href is None:
            raise ValueError("image nodes require a project-local href")
        if self.kind == "chart" and self.chart is None:
            raise ValueError("chart nodes require a native-ready chart contract")
        if self.kind == "table" and self.table is None:
            raise ValueError("table nodes require a native-ready table contract")
        return self


class SlideSceneGraph(SceneContract):
    schema_version: Literal[1] = 1
    workflow_run_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    slide_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    pnn: str = Field(pattern=r"^P\d{2,3}$")
    page_blueprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    author_attempt: int = Field(ge=1, le=5)
    background: str = "#F8FAFC"
    nodes: list[SceneNode] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_graph(self) -> SlideSceneGraph:
        if _HEX_COLOR.fullmatch(self.background) is None:
            raise ValueError("scene background must be a six-digit hex color")
        node_ids: list[str] = []

        def collect(node: SceneNode) -> None:
            node_ids.append(node.node_id)
            for child in node.children:
                collect(child)

        for node in self.nodes:
            collect(node)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("scene node IDs must be unique across the page")
        return self


@dataclass(frozen=True)
class ToolCallbacks:
    svg_gate: Callable[[str, Path, str], dict[str, Any]] | None = None
    render: Callable[[str, Path, str], dict[str, Any]] | None = None
    chart_gate: Callable[[str, Path, str], dict[str, Any]] | None = None
    visual_review: Callable[[Path, str], dict[str, Any]] | None = None


@dataclass(frozen=True)
class PresentationToolContext:
    project: Path
    request: WorkflowRequestV2
    blueprint: PageBlueprintArtifact
    blueprint_sha256: str
    fragments: tuple[dict[str, Any], ...]
    allowed_tools: frozenset[str]
    current_pnn: str
    stage: str
    author_attempt: int
    callbacks: ToolCallbacks = ToolCallbacks()


def design_catalog() -> dict[str, Any]:
    """Return closed tokens and semantic primitives, not executable components."""

    return {
        "schema": "instant-ppt.design-catalog.v1",
        "canvas": {"width": 1280, "height": 720, "safeMargin": 72, "grid": 8},
        "colors": {
            "background": "#F8FAFC",
            "panel": "#FFFFFF",
            "ink": "#0F172A",
            "body": "#1E293B",
            "muted": "#64748B",
            "line": "#CBD5E1",
            "accent": "#2563EB",
            "secondary": "#0F766E",
        },
        "typography": {
            "family": "Microsoft YaHei, Arial, sans-serif",
            "title": 38,
            "subtitle": 24,
            "body": 22,
            "annotation": 15,
        },
        "spacing": [8, 12, 16, 24, 32, 48, 64, 72],
        "primitives": [
            "text",
            "rect",
            "round-rect",
            "ellipse",
            "line",
            "group",
            "image",
            "native-chart",
            "native-table",
        ],
        "relationshipPatterns": [
            "comparison",
            "sequence",
            "process",
            "architecture",
            "cause-effect",
            "evidence-stack",
        ],
    }


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _sha_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _node_svg(node: SceneNode, project: Path, indent: str = "  ") -> list[str]:
    node_id = _escape(node.node_id)
    if node.kind == "group":
        lines = [
            f'{indent}<g id="{node_id}" data-pptx-bounds="{node.x:g} {node.y:g} '
            f'{node.width:g} {node.height:g}">'
        ]
        for child in node.children:
            lines.extend(_node_svg(child, project, indent + "  "))
        lines.append(f"{indent}</g>")
        return lines
    if node.kind == "text":
        lines = str(node.text).splitlines() or [""]
        rendered = [
            f'{indent}<text id="{node_id}" x="{node.x:g}" y="{node.y + node.font_size:g}" '
            f'font-family="{_escape(node.font_family)}" font-size="{node.font_size:g}" '
            f'font-weight="{node.font_weight}" fill="{node.text_color}" '
            f'text-anchor="{node.text_anchor}">'
        ]
        for index, line in enumerate(lines):
            dy = 0 if index == 0 else node.font_size * 1.25
            rendered.append(
                f'{indent}  <tspan x="{node.x:g}" dy="{dy:g}">{_escape(line)}</tspan>'
            )
        rendered.append(f"{indent}</text>")
        return rendered
    if node.kind == "shape":
        if node.shape in {"rect", "round-rect"}:
            radius = min(20, node.height / 4) if node.shape == "round-rect" else 0
            return [
                f'{indent}<rect id="{node_id}" x="{node.x:g}" y="{node.y:g}" '
                f'width="{node.width:g}" height="{node.height:g}" rx="{radius:g}" '
                f'fill="{node.fill}" stroke="{node.stroke}" '
                f'stroke-width="{node.stroke_width:g}"/>'
            ]
        if node.shape == "ellipse":
            return [
                f'{indent}<ellipse id="{node_id}" cx="{node.x + node.width / 2:g}" '
                f'cy="{node.y + node.height / 2:g}" rx="{node.width / 2:g}" '
                f'ry="{node.height / 2:g}" fill="{node.fill}" stroke="{node.stroke}" '
                f'stroke-width="{node.stroke_width:g}"/>'
            ]
        return [
            f'{indent}<line id="{node_id}" x1="{node.x:g}" y1="{node.y:g}" '
            f'x2="{node.x + node.width:g}" y2="{node.y + node.height:g}" '
            f'stroke="{node.stroke}" stroke-width="{node.stroke_width:g}"/>'
        ]
    if node.kind == "image":
        href = str(node.href)
        _validate_image_href(project, href)
        aspect = "xMidYMid meet" if node.crop == "contain" else "xMidYMid slice"
        return [
            f'{indent}<image id="{node_id}" x="{node.x:g}" y="{node.y:g}" '
            f'width="{node.width:g}" height="{node.height:g}" href="{_escape(href)}" '
            f'preserveAspectRatio="{aspect}"/>'
        ]
    if node.kind == "chart":
        return _chart_svg(node, indent)
    if node.kind == "table":
        return _table_svg(node, indent)
    raise ValueError(f"unsupported scene node kind: {node.kind}")


def _chart_svg(node: SceneNode, indent: str) -> list[str]:
    chart = node.chart
    if chart is None:
        raise ValueError("chart contract is required")
    values = [point.value for point in chart.values]
    axis_min = min(0.0, min(values))
    axis_max = max(1.0, max(values))
    if math.isclose(axis_min, axis_max):
        axis_max = axis_min + 1
    plot_x = node.x + 56
    plot_y = node.y + 40
    plot_width = max(40.0, node.width - 96)
    plot_height = max(40.0, node.height - 96)
    metadata = {
        "x": node.x,
        "y": node.y,
        "width": node.width,
        "height": node.height,
        "plot_area": {
            "x": plot_x,
            "y": plot_y,
            "width": plot_width,
            "height": plot_height,
        },
        "name": chart.object_key,
        "type": chart.chart_type,
        "categories": [point.label for point in chart.values],
        "series": [{"name": chart.unit, "values": values}],
        "show_legend": False,
        "source": {"text": chart.source_text},
    }
    lines = [
        f'{indent}<g id="{chart.object_key}" data-pptx-bounds="{node.x:g} {node.y:g} '
        f'{node.width:g} {node.height:g}" data-pptx-replace-with="chart">',
        f'{indent}  <metadata type="application/json">'
        + html.escape(json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))),
        f'{indent}  </metadata>',
        f'{indent}  <rect id="{chart.object_key}-panel" x="{node.x:g}" y="{node.y:g}" '
        f'width="{node.width:g}" height="{node.height:g}" rx="12" fill="{node.fill}" '
        f'stroke="{node.stroke}"/>',
        f'{indent}  <g id="{chart.object_key}-chart-area">',
    ]
    gap = plot_width / len(values)
    bar_width = min(100.0, gap * 0.58)
    scale = plot_height / (axis_max - axis_min)
    baseline_y = plot_y + axis_max * scale
    lines.append(
        f'{indent}    <!-- chart-plot-area: object={chart.object_key} | '
        f'{plot_x:g},{plot_y:g},{plot_x + plot_width:g},{plot_y + plot_height:g} -->'
    )
    for index, point in enumerate(chart.values):
        center = plot_x + gap * (index + 0.5)
        height = abs(point.value) * scale
        y = baseline_y - height if point.value >= 0 else baseline_y
        color = "#2563EB" if index == 0 else "#0F766E"
        lines.extend(
            [
                f'{indent}    <rect id="{chart.object_key}-bar-{index}" '
                f'x="{center - bar_width / 2:g}" y="{y:g}" width="{bar_width:g}" '
                f'height="{height:g}" rx="5" fill="{color}"/>',
                f'{indent}    <text id="{chart.object_key}-value-{index}" x="{center:g}" '
                f'y="{max(node.y + 18, y - 8):g}" text-anchor="middle" '
                'font-family="Arial, sans-serif" font-size="16" font-weight="700" '
                f'fill="#0F172A">{point.value:g} {_escape(chart.unit)}</text>',
                f'{indent}    <text id="{chart.object_key}-label-{index}" x="{center:g}" '
                f'y="{node.y + node.height - 18:g}" text-anchor="middle" '
                'font-family="Arial, sans-serif" font-size="14" '
                f'fill="#334155">{_escape(point.label)}</text>',
            ]
        )
    lines.extend(
        [
            f"{indent}  </g>",
            f'{indent}  <text id="{chart.object_key}-source" x="{node.x + 12:g}" '
            f'y="{node.y + node.height - 2:g}" '
            'font-family="Microsoft YaHei, Arial, sans-serif" font-size="11" '
            f'fill="#64748B">{_escape(chart.source_text)}</text>',
            f"{indent}</g>",
        ]
    )
    return lines


def _table_svg(node: SceneNode, indent: str) -> list[str]:
    table = node.table
    if table is None:
        raise ValueError("table contract is required")
    all_rows = [table.columns, *table.rows]
    column_width = node.width / len(table.columns)
    row_height = node.height / len(all_rows)
    metadata = {
        "name": table.object_key,
        "x": node.x,
        "y": node.y,
        "width": node.width,
        "height": node.height,
        "strict_grid": True,
        "columns": [{"text": value, "bold": True} for value in table.columns],
        "rows": [[{"text": value} for value in row] for row in table.rows],
        "style": {
            "font_family": "Microsoft YaHei",
            "font_size": 15,
            "header_fill": "#E2E8F0",
            "header_text": "#0F172A",
            "body_fill": "#FFFFFF",
            "body_text": "#1E293B",
            "band_row": True,
            "border_color": "#CBD5E1",
            "border_width": 1,
        },
    }
    lines = [
        f'{indent}<g id="{table.object_key}" data-pptx-bounds="{node.x:g} {node.y:g} '
        f'{node.width:g} {node.height:g}" data-pptx-replace-with="table">',
        f'{indent}  <metadata type="application/json">'
        + html.escape(json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))),
        f'{indent}  </metadata>',
    ]
    for row_index, row in enumerate(all_rows):
        for column_index, value in enumerate(row):
            x = node.x + column_index * column_width
            y = node.y + row_index * row_height
            fill = "#E2E8F0" if row_index == 0 else (
                "#F8FAFC" if row_index % 2 == 0 else "#FFFFFF"
            )
            weight = 700 if row_index == 0 else 400
            lines.extend(
                [
                    f'{indent}  <rect id="{table.object_key}-cell-{row_index}-{column_index}" '
                    f'x="{x:g}" y="{y:g}" width="{column_width:g}" '
                    f'height="{row_height:g}" fill="{fill}" stroke="#CBD5E1"/>',
                    f'{indent}  <text id="{table.object_key}-text-{row_index}-{column_index}" '
                    f'x="{x + 10:g}" y="{y + row_height / 2 + 6:g}" '
                    'font-family="Microsoft YaHei, Arial, sans-serif" font-size="15" '
                    f'font-weight="{weight}" fill="#1E293B">{_escape(value)}</text>',
                ]
            )
    lines.append(f"{indent}</g>")
    return lines


def render_scene_graph(graph: SlideSceneGraph, project: Path) -> str:
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720" data-pptx-page-role="content">',
        f'  <rect id="page-background" x="0" y="0" width="1280" height="720" '
        f'fill="{graph.background}" data-pptx-role="background"/>',
        '  <g id="page-content" data-pptx-bounds="0 0 1280 720">',
    ]
    for node in graph.nodes:
        lines.extend(_node_svg(node, project, "    "))
    lines.extend(["  </g>", "</svg>"])
    return "\n".join(lines) + "\n"


def _validate_image_href(project: Path, href: str) -> None:
    if not re.fullmatch(r"\.\./images/[A-Za-z0-9][A-Za-z0-9._-]{0,127}", href):
        raise ToolPolicyError("image href must target one direct project-local images asset")
    path = (project / "svg_output" / href).resolve()
    images = (project / "images").resolve()
    if path.parent != images or not path.is_file():
        raise ToolPolicyError("image href is missing or escapes the project images directory")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ToolPolicyError("image href must be PNG, JPEG, or WebP")


def validate_direct_svg(svg: str, project: Path) -> None:
    if len(svg.encode("utf-8")) > 1_500_000:
        raise ToolPolicyError("direct SVG exceeds the bounded authoring payload")
    if _SVG_FORBIDDEN_TEXT.search(svg):
        raise ToolPolicyError("direct SVG contains forbidden active or external content")
    try:
        root = DefusedET.fromstring(svg)
    except Exception as error:
        raise ToolPolicyError(f"direct SVG is not safe well-formed XML: {error}") from error
    if root.tag.rsplit("}", 1)[-1] != "svg" or root.attrib.get("viewBox") != "0 0 1280 720":
        raise ToolPolicyError("direct SVG must use the exact 1280x720 root viewBox")
    ids: list[str] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in _SVG_ALLOWED_TAGS:
            raise ToolPolicyError(f"direct SVG tag is not allowed: {tag}")
        element_id = element.attrib.get("id")
        if element_id:
            if _NODE_ID.fullmatch(element_id) is None:
                raise ToolPolicyError("direct SVG IDs must be stable kebab-case values")
            ids.append(element_id)
        for name, value in element.attrib.items():
            local_name = name.rsplit("}", 1)[-1].casefold()
            if local_name.startswith("on"):
                raise ToolPolicyError("direct SVG event handlers are forbidden")
            if "url(" in value.casefold() and not re.fullmatch(
                r"url\(#[a-z][a-z0-9-]{1,79}\)", value
            ):
                raise ToolPolicyError("direct SVG only allows local fragment paint references")
            if local_name in {"href", "xlink:href"}:
                if tag == "image":
                    _validate_image_href(project, value)
                elif not value.startswith("#"):
                    raise ToolPolicyError("direct SVG href must be a local fragment")
    if len(ids) != len(set(ids)):
        raise ToolPolicyError("direct SVG IDs must be unique")


class PresentationAgentToolRegistry:
    """Execute closed semantic tools and persist immutable observations."""

    def __init__(self, context: PresentationToolContext) -> None:
        if context.blueprint_sha256 != canonical_sha256(
            context.blueprint.model_dump(by_alias=True, mode="json")
        ):
            raise ToolPolicyError("tool context Page Blueprint hash is stale")
        if context.current_pnn not in {page.pnn for page in context.blueprint.pages}:
            raise ToolPolicyError("current page is not in the approved Blueprint roster")
        self.context = context
        self.project = context.project.resolve()
        self.project.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        input_sha256: str,
    ) -> dict[str, Any]:
        if _TOOL_ID.fullmatch(tool_call_id) is None:
            raise ToolPolicyError("toolCallId must be a ULID")
        if tool_name not in AGENT_TOOL_NAMES:
            raise ToolPolicyError(f"unknown Agent tool: {tool_name}")
        if tool_name not in self.context.allowed_tools:
            raise ToolPolicyError(f"Agent tool is not allowed by runtime policy: {tool_name}")
        if not re.fullmatch(r"[a-f0-9]{64}", input_sha256):
            raise ToolPolicyError("tool inputSha256 is invalid")
        evidence_path = self.project / "agent" / "tool-calls" / f"{tool_call_id}.json"
        if evidence_path.exists():
            existing = json.loads(evidence_path.read_text(encoding="utf-8"))
            if existing["argumentsSha256"] != canonical_sha256(arguments):
                raise ToolPolicyError("tool call ID was reused with different arguments")
            return existing
        started_at = datetime.now(UTC)
        output = self._dispatch(tool_name, arguments)
        output_sha256 = canonical_sha256(output)
        subject_sha256 = str(output.get("subjectSha256") or output_sha256)
        stale = list(WRITE_STALE_TARGETS) if tool_name in MUTATING_TOOLS else []
        record = {
            "schema": "instant-ppt.agent-tool-observation.v1",
            "toolCallId": tool_call_id,
            "workflowRunId": self.context.request.workflow_run_id,
            "stage": self.context.stage,
            "authorAttempt": self.context.author_attempt,
            "currentPnn": self.context.current_pnn,
            "toolName": tool_name,
            "argumentsSha256": canonical_sha256(arguments),
            "inputSha256": input_sha256,
            "outputSha256": output_sha256,
            "subjectSha256": subject_sha256,
            "stale": stale,
            "status": "succeeded",
            "observation": output,
            "startedAt": started_at.isoformat(),
            "completedAt": datetime.now(UTC).isoformat(),
        }
        _write_json(evidence_path, record)
        if stale:
            self._record_stale(tool_call_id, subject_sha256, stale)
        return record

    def _page(self) -> Any:
        return next(
            page
            for page in self.context.blueprint.pages
            if page.pnn == self.context.current_pnn
        )

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "read_approved_context":
            return self._read_approved_context(arguments)
        if name == "read_design_catalog":
            if arguments:
                raise ToolPolicyError("read_design_catalog accepts no arguments")
            return design_catalog()
        if name == "write_planning_artifact":
            return self._write_planning_artifact(arguments)
        if name == "write_or_patch_slide_svg":
            return self._write_slide(arguments)
        if name == "run_svg_gate":
            return self._run_page_callback("svg_gate", arguments)
        if name == "render_slide_or_deck":
            return self._run_page_callback("render", arguments)
        if name == "run_chart_gate":
            return self._run_page_callback("chart_gate", arguments)
        if name == "request_visual_review":
            return self._run_visual_review(arguments)
        if name == "complete_or_pause_stage":
            return self._complete_or_pause(arguments)
        raise ToolPolicyError(f"unimplemented Agent tool: {name}")

    def _read_approved_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested_pnn = str(arguments.get("pnn") or self.context.current_pnn)
        if requested_pnn != self.context.current_pnn:
            raise ToolPolicyError("Agent may only read the current page's full source context")
        page = self._page()
        approved_refs = set(page.evidence_refs)
        fragments = [
            {
                "fragmentId": str(fragment["fragmentId"]),
                "text": str(fragment["text"]),
                "textSha256": str(fragment.get("textSha256") or ""),
                "taint": "untrusted-source-data",
                "sourceInstructionsIgnored": True,
            }
            for fragment in self.context.fragments
            if str(fragment.get("fragmentId")) in approved_refs
        ]
        design_spec = self.project / "design_spec.md"
        spec_lock = self.project / "spec_lock.md"
        return {
            "schema": "instant-ppt.approved-agent-context.v1",
            "workflowRunId": self.context.request.workflow_run_id,
            "approvedSnapshotSha256": self.context.request.approval.snapshot_sha256,
            "pageBlueprintSha256": self.context.blueprint_sha256,
            "page": page.model_dump(by_alias=True, mode="json"),
            "roster": [
                {
                    "pnn": item.pnn,
                    "slideId": item.slide_id,
                    "order": item.order,
                    "role": item.role,
                    "visualForm": item.visual_form,
                }
                for item in self.context.blueprint.pages
            ],
            "fragments": fragments,
            "designSpec": (
                design_spec.read_text(encoding="utf-8") if design_spec.is_file() else None
            ),
            "specLock": spec_lock.read_text(encoding="utf-8") if spec_lock.is_file() else None,
        }

    def _write_planning_artifact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        filename = str(arguments.get("filename") or "")
        if _PLANNING_NAME.fullmatch(filename) is None:
            raise ToolPolicyError("planning artifact filename is outside the owned JSON namespace")
        payload = arguments.get("payload")
        if not isinstance(payload, dict):
            raise ToolPolicyError("planning artifact payload must be an object")
        forbidden = {"outline", "approval", "userReceipt", "approvedBy"}
        if forbidden & set(payload):
            raise ToolPolicyError("planning tools cannot modify approval or Outline authority")
        path = self.project / "analysis" / "agent-planning" / filename
        before = _sha_file(path) if path.is_file() else None
        _write_json(path, payload)
        return {
            "kind": "planning-artifact",
            "key": path.relative_to(self.project).as_posix(),
            "beforeSha256": before,
            "subjectSha256": _sha_file(path),
            "sizeBytes": path.stat().st_size,
        }

    def _write_slide(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested_pnn = str(arguments.get("pnn") or "")
        if requested_pnn != self.context.current_pnn or _PNN.fullmatch(requested_pnn) is None:
            raise ToolPolicyError("slide write must target the current approved PNN")
        page = self._page()
        mode = str(arguments.get("mode") or "scene-graph")
        svg_path = self.project / "svg_output" / f"slide_{page.order:02d}.svg"
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        before = _sha_file(svg_path) if svg_path.is_file() else None
        if mode == "scene-graph":
            raw_graph = arguments.get("sceneGraph")
            if not isinstance(raw_graph, dict):
                raise ToolPolicyError("scene-graph mode requires a structured sceneGraph")
            graph = SlideSceneGraph.model_validate(raw_graph)
            if (
                graph.workflow_run_id != self.context.request.workflow_run_id
                or graph.slide_id != page.slide_id
                or graph.pnn != page.pnn
                or graph.page_blueprint_sha256 != self.context.blueprint_sha256
                or graph.author_attempt != self.context.author_attempt
            ):
                raise ToolPolicyError("Scene Graph ownership/hash/attempt is stale or cross-page")
            self._validate_graph_against_page(graph, page)
            scene_path = self.project / "agent" / "scene-graphs" / f"{page.pnn}.json"
            _write_json(scene_path, graph.model_dump(by_alias=True, mode="json"))
            svg = render_scene_graph(graph, self.project)
            authoring_mode = "scene-graph"
        elif mode == "direct-svg":
            svg = str(arguments.get("svg") or "")
            validate_direct_svg(svg, self.project)
            self._validate_direct_svg_against_page(svg, page)
            scene_path = None
            authoring_mode = "validated-direct-svg"
        else:
            raise ToolPolicyError("slide write mode must be scene-graph or direct-svg")
        svg_path.write_text(svg.rstrip() + "\n", encoding="utf-8")
        validate_direct_svg(svg_path.read_text(encoding="utf-8"), self.project)
        return {
            "kind": "slide-svg",
            "pnn": page.pnn,
            "slideId": page.slide_id,
            "key": svg_path.relative_to(self.project).as_posix(),
            "sceneGraphKey": (
                scene_path.relative_to(self.project).as_posix() if scene_path is not None else None
            ),
            "authoringMode": authoring_mode,
            "beforeSha256": before,
            "subjectSha256": _sha_file(svg_path),
            "sizeBytes": svg_path.stat().st_size,
        }

    def _validate_graph_against_page(self, graph: SlideSceneGraph, page: Any) -> None:
        chart_nodes: list[SceneNode] = []
        table_nodes: list[SceneNode] = []

        def collect(node: SceneNode) -> None:
            if node.kind == "chart":
                chart_nodes.append(node)
            if node.kind == "table":
                table_nodes.append(node)
            for child in node.children:
                collect(child)

        for node in graph.nodes:
            collect(node)
        if chart_nodes:
            if page.chart_spec is None or len(chart_nodes) != 1:
                raise ToolPolicyError("native chart nodes must match the page Blueprint one-to-one")
            chart = chart_nodes[0].chart
            if chart is None or (
                chart.object_key != page.chart_spec.object_key
                or chart.unit != page.chart_spec.unit
                or [(point.label, point.value) for point in chart.values]
                != [(point.label, point.value) for point in page.chart_spec.values]
            ):
                raise ToolPolicyError("native chart data differs from approved Blueprint evidence")
        if page.chart_spec is not None and not chart_nodes:
            raise ToolPolicyError("chart Blueprint requires its native-ready Scene Graph object")
        if table_nodes and page.visual_form not in {"table", "mixed"}:
            raise ToolPolicyError("native table is not justified by the page visualForm")
        allowed_text = "\n".join(
            [page.assertion, *page.literal_constraints]
            + [block.text for block in page.content_blocks]
        ).casefold()
        for node in table_nodes:
            table = node.table
            if table is None:
                continue
            for value in [*table.columns, *(cell for row in table.rows for cell in row)]:
                if value.casefold() not in allowed_text:
                    raise ToolPolicyError(
                        "native table cell is absent from approved Blueprint content/literals"
                    )

    def _validate_direct_svg_against_page(self, svg: str, page: Any) -> None:
        root = DefusedET.fromstring(svg)
        chart_payloads: list[dict[str, Any]] = []
        table_payloads: list[dict[str, Any]] = []
        for element in root.iter():
            replacement = element.attrib.get("data-pptx-replace-with")
            if replacement not in {"chart", "table"}:
                continue
            metadata = next(
                (
                    child
                    for child in element
                    if child.tag.rsplit("}", 1)[-1] == "metadata"
                    and child.attrib.get("type") == "application/json"
                ),
                None,
            )
            if metadata is None or not (metadata.text or "").strip():
                raise ToolPolicyError("native replacement requires one JSON metadata child")
            try:
                payload = json.loads(str(metadata.text))
            except json.JSONDecodeError as error:
                raise ToolPolicyError("native replacement metadata is invalid JSON") from error
            if not isinstance(payload, dict):
                raise ToolPolicyError("native replacement metadata must be an object")
            (chart_payloads if replacement == "chart" else table_payloads).append(payload)
        if page.chart_spec is not None:
            if len(chart_payloads) != 1:
                raise ToolPolicyError("chart Blueprint requires one direct SVG chart marker")
            payload = chart_payloads[0]
            series = payload.get("series")
            if not isinstance(series, list) or len(series) != 1:
                raise ToolPolicyError("direct SVG chart must preserve one approved series")
            expected_values = [point.value for point in page.chart_spec.values]
            expected_labels = [point.label for point in page.chart_spec.values]
            if (
                payload.get("name") != page.chart_spec.object_key
                or payload.get("categories") != expected_labels
                or series[0].get("values") != expected_values
                or series[0].get("name") != page.chart_spec.unit
            ):
                raise ToolPolicyError("direct SVG chart differs from approved Blueprint evidence")
        elif chart_payloads:
            raise ToolPolicyError("direct SVG cannot add a chart absent from the Blueprint")
        if table_payloads and page.visual_form not in {"table", "mixed"}:
            raise ToolPolicyError("direct SVG table is not justified by the page visualForm")
        allowed_text = "\n".join(
            [page.assertion, *page.literal_constraints]
            + [block.text for block in page.content_blocks]
        ).casefold()
        for payload in table_payloads:
            values: list[str] = []
            for column in payload.get("columns") or []:
                values.append(str(column.get("text") if isinstance(column, dict) else column))
            for row in payload.get("rows") or []:
                for cell in row:
                    values.append(str(cell.get("text") if isinstance(cell, dict) else cell))
            if any(value.casefold() not in allowed_text for value in values):
                raise ToolPolicyError("direct SVG table contains unapproved Blueprint content")

    def _run_page_callback(self, callback_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        requested_pnn = str(arguments.get("pnn") or self.context.current_pnn)
        if requested_pnn != self.context.current_pnn:
            raise ToolPolicyError("page gate may only inspect the current page")
        callback = getattr(self.context.callbacks, callback_name)
        if callback is None:
            raise ToolPolicyError(f"Supervisor did not provide the {callback_name} capability")
        page = self._page()
        svg_path = self.project / "svg_output" / f"slide_{page.order:02d}.svg"
        if not svg_path.is_file():
            raise ToolPolicyError("page gate requires the current authored SVG")
        subject_sha256 = _sha_file(svg_path)
        report = callback(page.pnn, svg_path, subject_sha256)
        if not isinstance(report, dict):
            raise ToolPolicyError("Supervisor callback must return a structured observation")
        return {"subjectSha256": subject_sha256, "report": report}

    def _run_visual_review(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if arguments:
            raise ToolPolicyError("visual review target is fixed to the current rendered deck")
        callback = self.context.callbacks.visual_review
        if callback is None:
            raise ToolPolicyError("Supervisor did not provide the visual review capability")
        roster_hash = canonical_sha256(
            [
                {
                    "name": path.name,
                    "sha256": _sha_file(path),
                }
                for path in sorted((self.project / "svg_output").glob("slide_*.svg"))
            ]
        )
        report = callback(self.project, roster_hash)
        if not isinstance(report, dict):
            raise ToolPolicyError("visual reviewer must return a structured observation")
        return {"subjectSha256": roster_hash, "report": report}

    def _complete_or_pause(self, arguments: dict[str, Any]) -> dict[str, Any]:
        status = str(arguments.get("status") or "")
        if status not in {"completed", "paused", "failed"}:
            raise ToolPolicyError("stage termination status is invalid")
        reason = str(arguments.get("reason") or "").strip()
        if not reason:
            raise ToolPolicyError("stage termination requires an explicit reason")
        return {
            "subjectSha256": self.context.blueprint_sha256,
            "status": status,
            "reason": reason[:1000],
        }

    def _record_stale(
        self,
        tool_call_id: str,
        subject_sha256: str,
        stale: list[str],
    ) -> None:
        path = self.project / "validation" / "agent-stale.json"
        payload = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.is_file()
            else {
                "schema": "instant-ppt.agent-stale.v1",
                "workflowRunId": self.context.request.workflow_run_id,
                "entries": [],
            }
        )
        payload["entries"].append(
            {
                "toolCallId": tool_call_id,
                "pnn": self.context.current_pnn,
                "authorAttempt": self.context.author_attempt,
                "subjectSha256": subject_sha256,
                "stale": stale,
            }
        )
        payload["stateSha256"] = canonical_sha256(payload["entries"])
        _write_json(path, payload)
