"""Deterministic model double for offline Main Presentation Agent tests.

This provider is deliberately available only for the exact ``fake-agent@v1``
contract used by repository fixtures. Production requests use the configured
server-side text provider and never fall through to this implementation.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Any

from instant_ppt_worker.providers import TextCompletion


class DeterministicPresentationAgentProvider:
    """Select semantic tools from accumulated messages like a model test double."""

    provider_name = "deterministic-agent-fixture"

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        del response_format, max_completion_tokens
        if any(
            "Visual Review Agent" in str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        ):
            return _visual_review_completion(messages)
        phase_index, phase = _latest_phase(messages)
        observations = _observations(messages[phase_index + 1 :])
        decision = (
            _strategist_decision(phase, observations)
            if phase["role"] == "strategist"
            else _executor_decision(phase, observations)
        )
        content = json.dumps(decision, ensure_ascii=False, separators=(",", ":"))
        prompt_characters = sum(len(str(message.get("content") or "")) for message in messages)
        return TextCompletion(
            content=content,
            model="deterministic-agent-fixture@v1",
            prompt_tokens=max(1, prompt_characters // 4),
            completion_tokens=max(1, len(content) // 4),
        )


def _display_copy(value: str) -> str:
    """Render Markdown escapes as audience-visible punctuation without changing evidence."""

    return re.sub(r"\\([\\`*{}\[\]()#+.!_\-])", r"\1", value)


def _visual_review_completion(messages: list[dict[str, Any]]) -> TextCompletion:
    context: dict[str, Any] | None = None
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        text = next(
            (
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ),
            "",
        )
        marker = "reviewContext="
        start = text.find(marker)
        if start < 0:
            continue
        context, _ = json.JSONDecoder().raw_decode(text[start + len(marker) :])
        break
    if context is None:
        raise RuntimeError("visual review fixture received no bounded review context")
    payload = {"issues": []}
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    image_count = sum(
        1
        for message in messages
        for part in (message.get("content") if isinstance(message.get("content"), list) else [])
        if isinstance(part, dict) and part.get("type") == "image_url"
    )
    return TextCompletion(
        content=rendered,
        model="deterministic-visual-review-fixture@v1",
        prompt_tokens=1000 + image_count * 1000,
        completion_tokens=max(1, len(rendered) // 4),
    )


def _latest_phase(messages: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    for index in range(len(messages) - 1, -1, -1):
        content = str(messages[index].get("content") or "")
        match = re.search(
            r"<phase id='([^']+)' role='([^']+)'>.*?\n(\{.*\})\n</phase>",
            content,
            re.DOTALL,
        )
        if match:
            return index, {
                "phaseId": match.group(1),
                "role": match.group(2),
                "context": json.loads(match.group(3)),
            }
    raise RuntimeError("deterministic Agent fixture received no active phase")


def _observations(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for message in messages:
        content = str(message.get("content") or "")
        match = re.fullmatch(
            r"<tool-observation taint='supervisor-owned'>(.*)</tool-observation>",
            content,
            re.DOTALL,
        )
        if not match:
            continue
        value = json.loads(match.group(1))
        if isinstance(value, dict):
            values.append(value)
    return values


def _decision(
    role: str,
    *,
    tool_name: str | None = None,
    arguments: dict[str, Any] | None = None,
    reason: str,
    termination_reason: str | None = None,
) -> dict[str, Any]:
    if tool_name is not None:
        return {
            "schemaVersion": 1,
            "role": role,
            "action": "tool",
            "toolName": tool_name,
            "arguments": arguments or {},
            "reason": reason,
        }
    return {
        "schemaVersion": 1,
        "role": role,
        "action": "complete",
        "arguments": {},
        "reason": reason,
        "terminationReason": termination_reason or "phase-contract-satisfied",
    }


def _tool_names(observations: list[dict[str, Any]]) -> list[str]:
    return [str(value.get("toolName") or "") for value in observations]


def _strategist_decision(
    phase: dict[str, Any], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    observations = [value for value in observations if value.get("stage") == "strategist"]
    tools = _tool_names(observations)
    if "read_approved_context" not in tools:
        return _decision(
            "strategist",
            tool_name="read_approved_context",
            arguments={"pnn": "P01"},
            reason="Read the exact approved context before accepting the page strategy.",
        )
    if "read_design_spec_contract" not in tools:
        return _decision(
            "strategist",
            tool_name="read_design_spec_contract",
            reason="Read the complete PPT Master design-spec grammar before authoring.",
        )
    if "read_design_catalog" not in tools:
        return _decision(
            "strategist",
            tool_name="read_design_catalog",
            reason="Inspect the closed design vocabulary before fixing the system direction.",
        )
    if "write_planning_artifact" not in tools:
        context = phase["context"]
        outline = list(context["approvedOutline"])
        lines = [
            "<!-- ppt-master-schema: design-spec/v1 -->",
            f"# {context['intent']['title']} - Design Spec",
            "",
            "## I. Project Information",
            "",
            "| Item | Value |",
            "| --- | --- |",
            f"| Project Name | {context['intent']['title']} |",
            "| Canvas Format | ppt169 / 1280 × 720 |",
            f"| Page Count | {len(outline)} |",
            "| Primary Language | zh-CN |",
            f"| Target Audience | {context['intent']['audience']} |",
            f"| Communication Intent | {context['intent']['objective']} |",
            f"| Desired Audience Outcome | {context['intent']['objective']} |",
            f"| Core Message / Ask / Action | {context['intent']['objective']} |",
            "| Delivery Context | presenter-led |",
            "| Artifact Afterlife | review and hand-off |",
            "| Reading Mode | balanced |",
            "| Content Strategy | balanced default |",
            "| Design Style | conclusion-first editorial |",
            "| AI Image Acquisition Path | not applicable |",
            "| Generation Mode | continuous |",
            "| Spec Refinement | disabled |",
            "| Speaker Notes | enabled — workflow default |",
            "| Custom Animations | disabled — workflow default |",
            "| Narration Audio | disabled — workflow default |",
            "| Created Date | 2026-01-01 |",
            "",
            "## II. Canvas Specification",
            "",
            "| Property | Value |",
            "| --- | --- |",
            "| Format | ppt169 |",
            "| Dimensions | 1280 × 720 |",
            "| viewBox | `0 0 1280 720` |",
            "| Margins | 72 px |",
            "| Content Area | 1136 × 576 |",
            "",
            "## III. Visual Theme",
            "",
            "### Theme Style",
            "",
            "- **Mode**: briefing",
            "- **Visual style**: editorial",
            "- **Theme**: conclusion-first evidence hierarchy",
            "- **Tone**: restrained and authoritative",
            "",
            "### Color Scheme",
            "",
            "| Role | HEX | Purpose |",
            "| --- | --- | --- |",
            "| Background | #F7F8FA | primary field |",
            "| Secondary background | #E9EEF5 | panels |",
            "| Primary | #17324D | headings |",
            "| Accent | #1677FF | emphasis |",
            "| Secondary accent | #18A999 | secondary emphasis |",
            "| Body text | #1F2937 | readable copy |",
            "",
            "### AI Image Strategy",
            "",
            "- **Image Rendering**: editorial illustration",
            "- **Visual**: use only explicitly approved resources",
            "- **Mood**: factual and restrained",
            "",
            "## IV. Typography System",
            "",
            "### Font Plan",
            "",
            "| Role | Character (Reference) | Primary | English if non-English | Fallback tail |",
            "| --- | --- | --- | --- | --- |",
            "| Title | modern sans | Microsoft YaHei | Arial | sans-serif |",
            "| Body | neutral sans | Microsoft YaHei | Arial | sans-serif |",
            "",
            "- **Title stack**: Microsoft YaHei, Arial, sans-serif",
            "- **Body stack**: Microsoft YaHei, Arial, sans-serif",
            "",
            "### Font Size Hierarchy",
            "",
            "| Purpose | Anchor Size (px) |",
            "| --- | ---: |",
            "| Body | 22 |",
            "| Title | 48 |",
            "| Subtitle | 32 |",
            "| Annotation | 16 |",
            "",
            "## V. Layout Principles",
            "",
            "### Page Structure",
            "",
            "- **Header area**: stable title band",
            "- **Content area**: one governing assertion with evidence",
            "- **Footer area**: stable PNN at bottom-right",
            "",
            "### Spacing Specification",
            "",
            "| Element | Current Project |",
            "| --- | --- |",
            "| Safe margin | 72 px |",
            "| Content block gap | 32 px |",
            "| Icon-text gap | 12 px |",
            "",
            "## VI. Icon Usage Specification",
            "",
            "- **Primary bundled library**: none",
            "",
            "| Icon Path | Suitable Scenarios |",
            "| --- | --- |",
            "",
            "## VIII. Image Resource List",
            "",
            (
                "| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | "
                "Crop Policy | Acquire Via | Status | Reference | text_policy | page_role |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            "",
            "## IX. Content Outline",
            "",
        ]
        for index, resource in enumerate(context.get("preparedImages") or [], start=1):
            if resource.get("status") == "Resolved-Native":
                continue
            filename = str(resource.get("filename") or f"pending-image-{index:02d}.png")
            lines.insert(
                lines.index("## IX. Content Outline") - 1,
                "| "
                + " | ".join(
                    [
                        filename,
                        str(resource.get("dimensions") or "n/a"),
                        str(resource.get("ratio") or "n/a"),
                        str(resource.get("purpose") or "approved image resource"),
                        "Illustration",
                        str(resource.get("layoutPattern") or "editorial image beside native copy"),
                        str(resource.get("cropPolicy") or "adaptive"),
                        str(resource.get("acquireVia") or "placeholder"),
                        str(resource.get("status") or "Pending"),
                        ",".join(str(value) for value in resource.get("slideIds") or []),
                        "none",
                        "hero_page",
                    ]
                )
                + " |",
            )
        for page in outline:
            lines.extend(
                [
                    f"#### Slide {page['order']:02d} / {page['pnn']} - {page['title']}",
                    f"- **Audience move**: uncertain → {page['audienceQuestion']}",
                    "- **Layout**: one governing assertion with supporting evidence.",
                    f"- **Title**: {page['title']}",
                    f"- **Core message**: {page['audienceQuestion']}",
                    f"- **Content**: Complete the approved {page['role']} page from source facts.",
                    "",
                ]
            )
        lines.extend(
            [
                "## X. Speaker Notes Requirements",
                "",
                "- **Generation**: enabled",
                "- **Filename**: match each SVG filename under `notes/`",
                "- **Content**: explain the approved source facts page by page",
                "- **Total duration**: 6 minutes",
                "- **Notes style**: formal",
                "- **Presentation purpose**: inform and explain",
            ]
        )
        return _decision(
            "strategist",
            tool_name="write_planning_artifact",
            arguments={
                "filename": "design_spec.md",
                "content": "\n".join(lines),
            },
            reason="Directly persist the Strategist-authored design specification.",
        )
    return _decision(
        "strategist",
        reason="The approved context was transformed directly into the locked design direction.",
        termination_reason="strategist-plan-complete",
    )


def _executor_decision(phase: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    context = phase["context"]
    pnn = str(context["page"]["pnn"])
    if context.get("mode") == "visual-review":
        observations = [value for value in observations if value.get("stage") == phase["phaseId"]]
        if "request_visual_review" not in _tool_names(observations):
            return _decision(
                "executor",
                tool_name="request_visual_review",
                reason="Request read-only multimodal review of the current rendered deck hash.",
            )
        return _decision(
            "executor",
            reason="The hash-bound structured visual review observation is recorded.",
            termination_reason=f"visual-review-round-{context['reviewRound']}-observed",
        )
    expected_stage = (
        "visual-repair"
        if phase["phaseId"].startswith("visual-repair-")
        else ("svg-gate-repair" if phase["phaseId"].startswith("svg-gate-repair-") else "executor")
    )
    observations = [
        value
        for value in observations
        if value.get("stage") == expected_stage and value.get("currentPnn") == pnn
    ]
    tools = _tool_names(observations)
    if "read_approved_context" not in tools:
        return _decision(
            "executor",
            tool_name="read_approved_context",
            arguments={"pnn": pnn},
            reason="Read the exact page evidence, roster, Design Spec, and spec lock.",
        )
    if pnn == "P01" and "read_design_catalog" not in tools:
        return _decision(
            "executor",
            tool_name="read_design_catalog",
            reason="Establish the reusable visual system on the first page.",
        )
    write_indexes = [
        index
        for index, value in enumerate(observations)
        if value.get("toolName") == "write_or_patch_slide_svg"
    ]
    gate_indexes = [
        index for index, value in enumerate(observations) if value.get("toolName") == "run_svg_gate"
    ]
    latest_gate_passed = bool(
        gate_indexes
        and observations[gate_indexes[-1]].get("observation", {}).get("report", {}).get("passed")
        is True
    )
    needs_revision = bool(
        (pnn == "P01" or expected_stage == "svg-gate-repair")
        and gate_indexes
        and gate_indexes[-1] > write_indexes[-1]
        and not latest_gate_passed
    )
    if not write_indexes or needs_revision:
        write_arguments: dict[str, Any] = {
            "pnn": pnn,
            "mode": "direct-svg",
            "svg": _direct_svg(
                context,
                revision=max(int(context.get("authorAttempt") or 1), len(write_indexes) + 1),
            ),
        }
        if expected_stage == "visual-repair" and context.get("expectedBeforeSha256"):
            approved_context = next(
                value
                for value in reversed(observations)
                if value.get("toolName") == "read_approved_context"
            )
            current_svg = str(
                approved_context.get("observation", {})
                .get("currentAuthoringAsset", {})
                .get("svg", "")
            )
            write_arguments["svg"] = _atomic_fixture_visual_repair(
                current_svg,
                list(context.get("allowedVisualRepairTargetIds") or []),
            )
            write_arguments["expectedBeforeSha256"] = context["expectedBeforeSha256"]
        return _decision(
            "executor",
            tool_name="write_or_patch_slide_svg",
            arguments=write_arguments,
            reason=(
                "Revise the page using the complete checker observation."
                if write_indexes
                else "Author the page from approved context with editable semantic objects."
            ),
        )
    if (
        (expected_stage == "executor" and pnn == "P01") or expected_stage == "svg-gate-repair"
    ) and (not gate_indexes or gate_indexes[-1] < write_indexes[-1]):
        return _decision(
            "executor",
            tool_name="run_svg_gate",
            arguments={"pnn": pnn},
            reason="Run the mandatory first-page gate before authoring the remaining roster.",
        )
    return _decision(
        "executor",
        reason="The current page has an Agent-authored SVG and all required gates are satisfied.",
        termination_reason=f"{pnn.lower()}-agent-authoring-complete",
    )


def _atomic_fixture_visual_repair(svg: str, target_ids: list[str]) -> str:
    root = ET.fromstring(svg)
    for target_id in target_ids:
        target = next(
            (element for element in root.iter() if element.attrib.get("id") == target_id),
            None,
        )
        if target is None:
            continue
        for attribute in ("x", "y", "width", "height", "font-size"):
            raw_value = target.attrib.get(attribute)
            if raw_value is None:
                continue
            try:
                target.attrib[attribute] = f"{float(raw_value) + 1:g}"
            except ValueError:
                continue
            return ET.tostring(root, encoding="unicode")
    raise RuntimeError("visual repair fixture received no editable stable target")


def _wrapped(value: str, width: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= width:
        return compact
    lines: list[str] = []
    remainder = compact
    while remainder:
        cut = min(width, len(remainder))
        if cut < len(remainder):
            spaces = [remainder.rfind(mark, 0, cut + 1) for mark in (" ", "，", "；", "。")]
            best = max(spaces)
            if best >= width // 2:
                cut = best + 1
        lines.append(remainder[:cut])
        remainder = remainder[cut:]
    return "\n".join(lines[:4])


def _character_units(character: str) -> float:
    return 1.0 if unicodedata.east_asian_width(character) in {"W", "F"} else 0.56


def _wrap_units(value: str, capacity: float) -> list[str]:
    lines: list[str] = []
    for paragraph in value.replace("\r", "").split("\n"):
        remaining = " ".join(paragraph.split())
        if not remaining:
            lines.append("")
            continue
        while remaining:
            units = 0.0
            cut = 0
            last_break = 0
            for index, character in enumerate(remaining, start=1):
                next_units = units + _character_units(character)
                if next_units > capacity and cut:
                    break
                units = next_units
                cut = index
                if character in " \t，。；：、,.!?;:":
                    last_break = index
            if cut < len(remaining) and last_break >= max(1, cut // 2):
                cut = last_break
            lines.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
    return lines


def _fit_text(
    value: str,
    width: float,
    height: float,
    maximum: float,
    minimum: float = 15,
) -> tuple[str, float]:
    compact = " ".join(value.split())
    if not compact:
        return "", maximum
    size = maximum
    while size >= minimum:
        lines = _wrap_units(compact, max(1, width * 0.9 / size))
        if len(lines) * size * 1.25 <= height * 0.92:
            return "\n".join(lines), round(size, 1)
        size -= 0.5
    return "\n".join(_wrap_units(compact, max(1, width * 0.9 / minimum))), minimum


def _text_node(
    node_id: str,
    text: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    size: float,
    weight: int = 400,
    color: str = "#1E293B",
    text_anchor: str | None = None,
) -> dict[str, Any]:
    node = {
        "nodeId": node_id,
        "kind": "text",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "text": text,
        "fontSize": size,
        "fontWeight": weight,
        "textColor": color,
    }
    if text_anchor is not None:
        node["textAnchor"] = text_anchor
    return node


def _shape_node(
    node_id: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    stroke: str = "#CBD5E1",
    shape: str = "round-rect",
) -> dict[str, Any]:
    return {
        "nodeId": node_id,
        "kind": "shape",
        "shape": shape,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "fill": fill,
        "stroke": stroke,
    }


def _stacked_text_nodes(
    prefix: str,
    values: list[str],
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    maximum_size: float,
    weight: int = 500,
    color: str = "#1E293B",
) -> list[dict[str, Any]]:
    rendered = values or [""]
    slot = height / len(rendered)
    nodes: list[dict[str, Any]] = []
    for index, value in enumerate(rendered):
        if not value:
            continue
        fitted, size = _fit_text(value, width, slot, maximum_size)
        nodes.append(
            _text_node(
                f"{prefix}-{index + 1}",
                fitted,
                x=x,
                y=y + index * slot,
                width=width,
                height=slot,
                size=size,
                weight=weight,
                color=color,
            )
        )
    return nodes


def _fixture_layout(context: dict[str, Any], *, revision: int) -> list[dict[str, Any]]:
    page = context["page"]
    slide = context["slide"]
    title = _wrapped(_display_copy(str(slide["title"])), 28)
    body = [_display_copy(str(value)) for value in slide.get("body") or []]
    role = str(page["role"])
    accent = "#0F766E" if revision > 1 else "#2563EB"
    nodes: list[dict[str, Any]] = [
        _shape_node(
            "top-rule",
            x=0,
            y=0,
            width=1280,
            height=12,
            fill=accent,
            stroke=accent,
            shape="rect",
        ),
        _text_node(
            "page-label",
            f"{page['pnn']}  ·  {role.upper()}",
            x=72,
            y=38,
            width=300,
            height=28,
            size=15,
            weight=600,
            color="#2563EB",
        ),
        _text_node(
            "title",
            title,
            x=72,
            y=76,
            width=1136,
            height=106,
            size=64 if role == "cover" else 48,
            weight=700,
            color="#0F172A",
        ),
    ]
    chart = context.get("chart")
    image_href = context.get("imageHref")
    if chart:
        nodes.extend(
            [
                {
                    "nodeId": "evidence-chart",
                    "kind": "chart",
                    "x": 72,
                    "y": 210,
                    "width": 780,
                    "height": 410,
                    "fill": "#FFFFFF",
                    "stroke": "#CBD5E1",
                    "chart": {
                        "objectKey": chart["objectKey"],
                        "chartType": "column",
                        "values": [
                            {"label": label, "value": value} for label, value in chart["values"]
                        ],
                        "unit": chart["unit"],
                        "sourceText": str(chart["context"]),
                    },
                },
                _shape_node(
                    "insight-panel",
                    x=884,
                    y=210,
                    width=324,
                    height=410,
                    fill="#E0F2FE",
                    stroke="#7DD3FC",
                ),
                _text_node(
                    "insight-kicker",
                    "KEY TAKEAWAY",
                    x=916,
                    y=246,
                    width=260,
                    height=28,
                    size=15,
                    weight=700,
                    color="#0369A1",
                ),
                *_stacked_text_nodes(
                    "insight-copy",
                    body,
                    x=916,
                    y=292,
                    width=260,
                    height=250,
                    maximum_size=21,
                    weight=600,
                    color="#0F172A",
                ),
            ]
        )
    elif image_href:
        nodes.extend(
            [
                {
                    "nodeId": "approved-image",
                    "kind": "image",
                    "x": 72,
                    "y": 210,
                    "width": 570,
                    "height": 410,
                    "href": image_href,
                    "crop": str(context.get("imageCrop") or "cover"),
                },
                _shape_node(
                    "evidence-panel",
                    x=682,
                    y=210,
                    width=526,
                    height=410,
                    fill="#FFFFFF",
                ),
                *_stacked_text_nodes(
                    "evidence-copy",
                    body,
                    x=722,
                    y=250,
                    width=446,
                    height=320,
                    maximum_size=24,
                    weight=500,
                ),
            ]
        )
    elif role in {"comparison", "risk_action"}:
        left = body[0] if body else str(page["assertion"])
        right = (
            body[1]
            if len(body) > 1
            else "对比口径：仅呈现已批准的官方材料；未提供的数据不作推断。"
            if role == "comparison"
            else "建议：先在受控范围复核本页披露的能力与安全边界，再决定接入节奏。"
        )
        fitted_left, left_size = _fit_text(left, 456, 250, 25)
        fitted_right, right_size = _fit_text(right, 488, 250, 25)
        nodes.extend(
            [
                _shape_node("left-panel", x=72, y=220, width=536, height=380, fill="#FFFFFF"),
                _shape_node(
                    "right-panel",
                    x=640,
                    y=220,
                    width=568,
                    height=380,
                    fill="#ECFDF5",
                    stroke="#99F6E4",
                ),
                _text_node(
                    "left-copy",
                    fitted_left,
                    x=112,
                    y=270,
                    width=456,
                    height=250,
                    size=left_size,
                    weight=600,
                ),
                _text_node(
                    "right-copy",
                    fitted_right,
                    x=680,
                    y=270,
                    width=488,
                    height=250,
                    size=right_size,
                    weight=600,
                    color="#115E59",
                ),
            ]
        )
    elif role == "timeline":
        nodes.append(
            _shape_node(
                "timeline-axis",
                x=120,
                y=410,
                width=1040,
                height=4,
                fill="#94A3B8",
                stroke="#94A3B8",
                shape="rect",
            )
        )
        statements = (body or [str(page["assertion"])])[:3]
        positions = {
            1: [490],
            2: [260, 760],
            3: [120, 490, 860],
        }[len(statements)]
        for index, (statement, x) in enumerate(zip(statements, positions, strict=True)):
            fitted_statement, statement_size = _fit_text(statement, 300, 120, 18)
            nodes.extend(
                [
                    _shape_node(
                        f"milestone-{index + 1}",
                        x=x,
                        y=382,
                        width=58,
                        height=58,
                        fill="#2563EB" if index == 0 else "#0F766E",
                        stroke="#FFFFFF",
                        shape="ellipse",
                    ),
                    _text_node(
                        f"milestone-copy-{index + 1}",
                        fitted_statement,
                        x=x,
                        y=470,
                        width=300,
                        height=120,
                        size=statement_size,
                        weight=600,
                    ),
                ]
            )
    else:
        copy = "\n".join(body) or str(page["assertion"])
        nodes.extend(
            [
                _shape_node(
                    "statement-panel",
                    x=72,
                    y=220,
                    width=1136,
                    height=360,
                    fill="#FFFFFF" if revision == 1 else "#EFF6FF",
                ),
                _shape_node(
                    "statement-accent",
                    x=72,
                    y=220,
                    width=18,
                    height=360,
                    fill="#0F766E",
                    stroke="#0F766E",
                    shape="rect",
                ),
                *_stacked_text_nodes(
                    "statement-copy",
                    body or [copy],
                    x=130,
                    y=280,
                    width=1010,
                    height=230,
                    maximum_size=27 if role == "cover" else 24,
                    weight=600,
                ),
            ]
        )
    nodes.append(
        _text_node(
            "evidence-footer",
            "依据：已批准官方材料（封闭语料）",
            x=72,
            y=666,
            width=600,
            height=24,
            size=15,
            color="#64748B",
        )
    )
    nodes.append(
        _text_node(
            "page-number",
            str(page["pnn"]),
            x=1208,
            y=648,
            width=48,
            height=24,
            size=15,
            color="#64748B",
            text_anchor="end",
        )
    )
    return nodes


def _direct_svg(context: dict[str, Any], *, revision: int) -> str:
    """Render the deterministic test fixture straight to the production SVG contract."""

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def render(node: dict[str, Any]) -> list[str]:
        node_id = esc(node["nodeId"])
        kind = node["kind"]
        x = float(node["x"])
        y = float(node["y"])
        width = float(node["width"])
        height = float(node["height"])
        if kind == "text":
            size = float(node.get("fontSize") or 22)
            parts = str(node.get("text") or "").splitlines() or [""]
            spans = "".join(
                f'<tspan x="{x:g}" dy="{0 if index == 0 else size * 1.25:g}">{esc(part)}</tspan>'
                for index, part in enumerate(parts)
            )
            return [
                f'<text id="{node_id}" x="{x:g}" y="{y + size:g}" '
                f'font-family="Microsoft YaHei, Arial, sans-serif" font-size="{size:g}" '
                f'font-weight="{int(node.get("fontWeight") or 400)}" '
                f'text-anchor="{esc(node.get("textAnchor") or "start")}" '
                f'fill="{esc(node.get("textColor") or "#1E293B")}">{spans}</text>'
            ]
        if kind == "shape":
            fill = esc(node.get("fill") or "#FFFFFF")
            stroke = esc(node.get("stroke") or "#CBD5E1")
            shape = node.get("shape") or "round-rect"
            if shape == "line":
                return [
                    f'<line id="{node_id}" x1="{x:g}" y1="{y:g}" '
                    f'x2="{x + width:g}" y2="{y + height:g}" stroke="{stroke}"/>'
                ]
            if shape == "ellipse":
                return [
                    f'<ellipse id="{node_id}" cx="{x + width / 2:g}" '
                    f'cy="{y + height / 2:g}" rx="{width / 2:g}" ry="{height / 2:g}" '
                    f'fill="{fill}" stroke="{stroke}"/>'
                ]
            radius = 0 if shape == "rect" else min(20, height / 4)
            return [
                f'<rect id="{node_id}" x="{x:g}" y="{y:g}" width="{width:g}" '
                f'height="{height:g}" rx="{radius:g}" fill="{fill}" stroke="{stroke}"/>'
            ]
        if kind == "image":
            aspect = "meet" if node.get("crop") == "contain" else "slice"
            return [
                f'<image id="{node_id}" x="{x:g}" y="{y:g}" width="{width:g}" '
                f'height="{height:g}" href="{esc(node["href"])}" '
                f'preserveAspectRatio="xMidYMid {aspect}"/>'
            ]
        if kind == "chart":
            chart = node["chart"]
            values = [point["value"] for point in chart["values"]]
            metadata = {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "name": chart["objectKey"],
                "type": chart["chartType"],
                "categories": [point["label"] for point in chart["values"]],
                "series": [{"name": chart["unit"], "values": values}],
                "show_legend": False,
                "source": {"text": chart["sourceText"]},
            }
            bars = []
            maximum = max([abs(float(value)) for value in values] or [1.0]) or 1.0
            bar_width = max(12.0, (width - 96) / max(1, len(values)) - 12)
            for index, value in enumerate(values):
                bar_height = (height - 120) * abs(float(value)) / maximum
                bar_x = x + 56 + index * (bar_width + 12)
                bars.append(
                    f'<rect id="{node_id}-bar-{index + 1}" x="{bar_x:g}" '
                    f'y="{y + height - 48 - bar_height:g}" width="{bar_width:g}" '
                    f'height="{bar_height:g}" fill="#2563EB"/>'
                )
            return [
                f'<g id="{node_id}" data-pptx-bounds="{x:g} {y:g} {width:g} {height:g}" '
                'data-pptx-replace-with="chart">',
                '<metadata type="application/json">'
                + html.escape(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
                + "</metadata>",
                f"<!-- chart-plot-area: object={esc(chart['objectKey'])} -->",
                f'<rect id="{node_id}-panel" x="{x:g}" y="{y:g}" width="{width:g}" '
                f'height="{height:g}" rx="12" fill="#FFFFFF" stroke="#CBD5E1"/>',
                *bars,
                "</g>",
            ]
        raise ValueError(f"unsupported deterministic fixture element: {kind}")

    page_role = esc(str(context["page"]["role"]).replace("_", "-"))
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        f'viewBox="0 0 1280 720" data-pptx-page-role="{page_role}">',
        '<rect id="page-background" x="0" y="0" width="1280" height="720" '
        'fill="#F8FAFC" data-pptx-role="background"/>',
        '<g id="page-content" data-pptx-bounds="0 0 1280 720">',
    ]
    for item in _fixture_layout(context, revision=revision):
        lines.extend(render(item))
    lines.extend(["</g>", "</svg>"])
    return "\n".join(lines) + "\n"
