"""Constrained semantic authoring tools for the Main Presentation Agent.

The registry deliberately exposes page/domain operations instead of shell,
network, database, or general filesystem access.  Every mutation is scoped to
the current run and page and emits hash-bound evidence plus stale propagation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from defusedxml import ElementTree as DefusedET
from pydantic import ValidationError

from instant_ppt_worker.canonical import canonical_sha256
from instant_ppt_worker.workflow_models import ApprovedOutlineSlide, WorkflowRequestV2

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
_DESIGN_SPEC_MARKER = "<!-- ppt-master-schema: design-spec/v1 -->"
_DESIGN_SPEC_REQUIRED_SECTIONS = (
    "I. Project Information",
    "II. Canvas Specification",
    "III. Visual Theme",
    "IV. Typography System",
    "V. Layout Principles",
    "VI. Icon Usage Specification",
    "VIII. Image Resource List",
    "IX. Content Outline",
)
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
    fragments: tuple[dict[str, Any], ...]
    allowed_tools: frozenset[str]
    current_pnn: str
    stage: str
    author_attempt: int
    prepared_images: tuple[dict[str, Any], ...] = ()
    callbacks: ToolCallbacks = ToolCallbacks()
    required_authoring_mode: Literal["direct-svg"] | None = None


def design_catalog(*, native_charts_enabled: bool = True) -> dict[str, Any]:
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
            "title": 48,
            "coverTitle": 64,
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
            *(["native-chart"] if native_charts_enabled else []),
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
        if context.current_pnn not in {page.pnn for page in context.request.outline}:
            raise ToolPolicyError("current page is not in the approved Outline roster")
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
        author_turn_id: str | None = None,
        usage_before: dict[str, int] | None = None,
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
        try:
            output = self._dispatch(tool_name, arguments)
        except ToolPolicyError:
            raise
        except (ValidationError, ValueError) as error:
            raise ToolPolicyError(f"Agent tool arguments are invalid: {error}") from error
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
            "authorTurnId": author_turn_id,
            "modelVersion": self.context.request.versions.model,
            "promptVersion": self.context.request.versions.prompt,
            "referenceVersion": self.context.request.versions.reference,
            "usageBefore": usage_before or {},
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

    def _page(self) -> ApprovedOutlineSlide:
        return next(
            page for page in self.context.request.outline if page.pnn == self.context.current_pnn
        )

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "read_approved_context":
            return self._read_approved_context(arguments)
        if name == "read_design_catalog":
            if arguments:
                raise ToolPolicyError("read_design_catalog accepts no arguments")
            return design_catalog(
                native_charts_enabled=self.context.request.production.native_charts
            )
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
        fragments = [
            {
                "fragmentId": str(fragment["fragmentId"]),
                "text": str(fragment["text"]),
                "textSha256": str(fragment.get("textSha256") or ""),
                "taint": "untrusted-source-data",
                "sourceInstructionsIgnored": True,
            }
            for fragment in self.context.fragments
        ]
        design_spec = self.project / "design_spec.md"
        spec_lock = self.project / "spec_lock.md"
        current_authoring_asset: dict[str, Any] | None = None
        if self.context.required_authoring_mode == "direct-svg":
            svg_path = self.project / "svg_output" / f"slide_{page.order:02d}.svg"
            if not svg_path.is_file():
                raise ToolPolicyError("direct SVG repair requires the current owned page SVG")
            current_authoring_asset = {
                "mode": "direct-svg",
                "subjectSha256": _sha_file(svg_path),
                "svg": svg_path.read_text(encoding="utf-8"),
            }
        return {
            "schema": "instant-ppt.approved-agent-context.v1",
            "workflowRunId": self.context.request.workflow_run_id,
            "approvedSnapshotSha256": self.context.request.approval.snapshot_sha256,
            "page": page.model_dump(by_alias=True, mode="json"),
            "roster": [
                {
                    "pnn": item.pnn,
                    "slideId": item.slide_id,
                    "order": item.order,
                    "role": item.role,
                    "title": item.title,
                    "audienceQuestion": item.audience_question,
                }
                for item in self.context.request.outline
            ],
            "fragments": fragments,
            "intent": self.context.request.intent.model_dump(by_alias=True, mode="json"),
            "template": self.context.request.template.model_dump(by_alias=True, mode="json"),
            "imagePolicy": self.context.request.image.model_dump(by_alias=True, mode="json"),
            "preparedImages": list(self.context.prepared_images),
            "visualReviewPolicy": {
                "required": self.context.request.authoring.visual_review_required,
                "policyVersion": self.context.request.authoring.visual_review_policy_version,
                "maxRounds": self.context.request.authoring.resolved_visual_review_max_rounds(),
            },
            "designSpec": (
                design_spec.read_text(encoding="utf-8") if design_spec.is_file() else None
            ),
            "specLock": spec_lock.read_text(encoding="utf-8") if spec_lock.is_file() else None,
            "currentAuthoringAsset": current_authoring_asset,
        }

    def _write_planning_artifact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        filename = str(arguments.get("filename") or "")
        if filename != "design_spec.md":
            raise ToolPolicyError("Strategist may write only the canonical design_spec.md")
        content = str(arguments.get("content") or "").strip()
        if not content.startswith(_DESIGN_SPEC_MARKER):
            raise ToolPolicyError("design_spec.md requires the canonical schema marker")
        if len(content.encode("utf-8")) > 500_000:
            raise ToolPolicyError("design_spec.md exceeds the bounded planning payload")
        section_positions: list[int] = []
        for section in _DESIGN_SPEC_REQUIRED_SECTIONS:
            match = re.search(rf"(?m)^## {re.escape(section)}\s*$", content)
            if match is None:
                raise ToolPolicyError(f"design_spec.md is missing required section: {section}")
            section_positions.append(match.start())
        speaker_notes = re.search(
            r"(?m)^## X\. Speaker Notes (?:Requirements|Plan|Strategy)\s*$", content
        )
        if speaker_notes is None:
            raise ToolPolicyError("design_spec.md is missing the speaker-notes section")
        section_positions.append(speaker_notes.start())
        if section_positions != sorted(section_positions):
            raise ToolPolicyError("design_spec.md sections must follow the canonical order")
        for page in self.context.request.outline:
            if page.pnn not in content or page.title not in content:
                raise ToolPolicyError(
                    f"design_spec.md must include approved page identity and title for {page.pnn}"
                )
            block = re.search(
                rf"(?ms)^#### Slide\s+\d+\b[^\n]*\b{re.escape(page.pnn)}\b[^\n]*"
                rf"\n(?P<body>.*?)(?=^#### Slide\s+\d+\b|^## X\.|\Z)",
                content,
            )
            if (
                block is None
                or re.search(r"(?mi)^- (?:\*\*)?Audience move(?:\*\*)?:\s*\S", block.group("body"))
                is None
            ):
                raise ToolPolicyError(
                    f"design_spec.md requires an Audience move in the slide block for {page.pnn}"
                )
        path = self.project / filename
        before = _sha_file(path) if path.is_file() else None
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        return {
            "kind": "design-spec",
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
        raw_mode = str(arguments.get("mode") or "direct-svg").strip().casefold()
        if re.sub(r"[^a-z]", "", raw_mode) != "directsvg":
            raise ToolPolicyError("slide write mode must be direct-svg")
        mode = "direct-svg"
        if (
            self.context.required_authoring_mode is not None
            and mode != self.context.required_authoring_mode
        ):
            raise ToolPolicyError(
                f"{self.context.stage} must preserve the current page authoring mode: "
                f"{self.context.required_authoring_mode}"
            )
        svg_path = self.project / "svg_output" / f"slide_{page.order:02d}.svg"
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        before = _sha_file(svg_path) if svg_path.is_file() else None
        svg = str(arguments.get("svg") or "")
        validate_direct_svg(svg, self.project)
        self._validate_direct_svg_against_page(svg, page)
        svg_path.write_text(svg.rstrip() + "\n", encoding="utf-8")
        validate_direct_svg(svg_path.read_text(encoding="utf-8"), self.project)
        return {
            "kind": "slide-svg",
            "pnn": page.pnn,
            "slideId": page.slide_id,
            "key": svg_path.relative_to(self.project).as_posix(),
            "authoringMode": "validated-direct-svg",
            "beforeSha256": before,
            "subjectSha256": _sha_file(svg_path),
            "sizeBytes": svg_path.stat().st_size,
        }

    def _validate_direct_svg_against_page(self, svg: str, page: Any) -> None:
        root = DefusedET.fromstring(svg)
        page_role = root.attrib.get("data-pptx-page-role")
        if not page_role:
            raise ToolPolicyError("direct SVG root requires data-pptx-page-role")
        expected_page_role = str(page.role).replace("_", "-")
        if page_role != expected_page_role:
            raise ToolPolicyError(
                "direct SVG page role must equal the kebab-case approved Outline role "
                f"{expected_page_role}"
            )
        text_elements = [
            element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "text"
        ]
        outline = next(item for item in self.context.request.outline if item.pnn == page.pnn)
        normalized_outline_title = "".join(outline.title.split()).casefold()
        title_elements = [
            element
            for element in text_elements
            if (
                (title_id := str(element.attrib.get("id") or "")) == "title"
                or title_id.startswith("title-")
                or title_id.endswith("-title")
                or element.attrib.get("data-pptx-role") == "title"
            )
        ]
        if not title_elements:
            title_elements = [
                element
                for element in text_elements
                if normalized_outline_title
                in "".join("".join(element.itertext()).split()).casefold()
            ]
        if len(title_elements) != 1:
            raise ToolPolicyError("direct SVG requires exactly one stable title text element")
        title_text = "".join(title_elements[0].itertext()).strip()
        if normalized_outline_title not in "".join(title_text.split()).casefold():
            raise ToolPolicyError("direct SVG title must preserve the approved outline title")
        raw_title_size = str(title_elements[0].attrib.get("font-size") or "").removesuffix("px")
        try:
            title_size = float(raw_title_size)
        except ValueError as error:
            raise ToolPolicyError("direct SVG title requires a numeric font-size") from error
        minimum_title_size = 64.0 if page.role == "cover" else 48.0
        if title_size < minimum_title_size:
            raise ToolPolicyError(
                f"direct SVG title font-size must be at least {minimum_title_size:g}px"
            )
        page_number_elements = [
            element for element in text_elements if "".join(element.itertext()).strip() == page.pnn
        ]
        if len(page_number_elements) != 1:
            raise ToolPolicyError(
                f"direct SVG requires exactly one page number equal to {page.pnn}"
            )
        page_number = page_number_elements[0]
        try:
            page_number_x = float(str(page_number.attrib.get("x") or "0"))
            page_number_y = float(str(page_number.attrib.get("y") or "0"))
        except ValueError as error:
            raise ToolPolicyError("direct SVG page number requires numeric x/y") from error
        if (
            page_number_x < 1100
            or page_number_y < 640
            or page_number.attrib.get("text-anchor") != "end"
        ):
            raise ToolPolicyError(
                "direct SVG page number must use the consistent bottom-right footer position"
            )
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
        approved_source = "\n".join(str(item.get("text") or "") for item in self.context.fragments)
        approved_outline = "\n".join(
            f"{item.title}\n{item.audience_question}" for item in self.context.request.outline
        )
        design_spec = self.project / "design_spec.md"
        approved_text = (
            approved_source
            + "\n"
            + approved_outline
            + "\n"
            + (design_spec.read_text(encoding="utf-8") if design_spec.is_file() else "")
        ).casefold()
        for payload in chart_payloads:
            categories = payload.get("categories")
            series = payload.get("series")
            if not isinstance(categories, list) or not categories:
                raise ToolPolicyError("direct SVG chart requires non-empty categories")
            if not isinstance(series, list) or not series:
                raise ToolPolicyError("direct SVG chart requires at least one series")
            if any(str(value).casefold() not in approved_text for value in categories):
                raise ToolPolicyError("direct SVG chart categories lack approved source support")
            for item in series:
                if not isinstance(item, dict) or not isinstance(item.get("values"), list):
                    raise ToolPolicyError("direct SVG chart series is malformed")
                if len(item["values"]) != len(categories):
                    raise ToolPolicyError("direct SVG chart values must match category count")
                for value in item["values"]:
                    rendered = f"{float(value):g}"
                    if rendered not in approved_source:
                        raise ToolPolicyError(
                            "direct SVG chart numeric values lack approved source support"
                        )
        for payload in table_payloads:
            values: list[str] = []
            for column in payload.get("columns") or []:
                values.append(str(column.get("text") if isinstance(column, dict) else column))
            for row in payload.get("rows") or []:
                for cell in row:
                    values.append(str(cell.get("text") if isinstance(cell, dict) else cell))
            if any(value.casefold() not in approved_text for value in values):
                raise ToolPolicyError("direct SVG table contains unsupported source content")

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
            "subjectSha256": (
                _sha_file(self.project / "design_spec.md")
                if (self.project / "design_spec.md").is_file()
                else self.context.request.approval.snapshot_sha256
            ),
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
