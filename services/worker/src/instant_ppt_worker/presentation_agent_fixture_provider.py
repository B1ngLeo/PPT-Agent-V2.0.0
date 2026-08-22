"""Deterministic model double for offline Main Presentation Agent tests.

This provider is deliberately available only for the exact ``fake-agent@v1``
contract used by repository fixtures. Production requests use the configured
server-side text provider and never fall through to this implementation.
"""

from __future__ import annotations

import json
import re
import unicodedata
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
        raise RuntimeError("visual review fixture received no hash-bound review context")
    payload = {
        "schemaVersion": 1,
        "workflowRunId": context["workflowRunId"],
        "reviewRound": context["reviewRound"],
        "subjectSha256": context["subjectSha256"],
        "renderSetSha256": context["renderSetSha256"],
        "contactSheetSha256": context["contactSheetSha256"],
        "passed": True,
        "issues": [],
        "summary": "Fixture reviewer found no blocking visual issue in the rendered roster.",
    }
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
    if "read_design_catalog" not in tools:
        return _decision(
            "strategist",
            tool_name="read_design_catalog",
            reason="Inspect the closed design vocabulary before fixing the system direction.",
        )
    if "write_planning_artifact" not in tools:
        context = phase["context"]
        proposal = context["pageBlueprintProposal"]
        return _decision(
            "strategist",
            tool_name="write_planning_artifact",
            arguments={
                "filename": "strategist-plan.json",
                "payload": {
                    "schema": "instant-ppt.strategist-plan.v1",
                    "workflowRunId": context["workflowRunId"],
                    "proposalSha256": context["proposalSha256"],
                    "pageCount": len(proposal["pages"]),
                    "roster": [page["pnn"] for page in proposal["pages"]],
                    "decision": "accepted-with-semantic-page-ownership",
                },
            },
            reason="Persist the model-selected storyline and page ownership decision.",
        )
    return _decision(
        "strategist",
        reason="The proposal, evidence ownership, and design vocabulary were inspected and fixed.",
        termination_reason="strategist-plan-complete",
    )


def _executor_decision(
    phase: dict[str, Any], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    context = phase["context"]
    pnn = str(context["page"]["pnn"])
    if context.get("mode") == "visual-review":
        observations = [
            value
            for value in observations
            if value.get("stage") == phase["phaseId"]
        ]
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
        "visual-repair" if phase["phaseId"].startswith("visual-repair-") else "executor"
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
        index
        for index, value in enumerate(observations)
        if value.get("toolName") == "run_svg_gate"
    ]
    latest_gate_passed = bool(
        gate_indexes
        and observations[gate_indexes[-1]]
        .get("observation", {})
        .get("report", {})
        .get("passed")
        is True
    )
    needs_revision = bool(
        pnn == "P01"
        and gate_indexes
        and gate_indexes[-1] > write_indexes[-1]
        and not latest_gate_passed
    )
    if not write_indexes or needs_revision:
        return _decision(
            "executor",
            tool_name="write_or_patch_slide_svg",
            arguments={
                "pnn": pnn,
                "mode": "scene-graph",
                "sceneGraph": _scene_graph(
                    context,
                    revision=max(
                        int(context.get("authorAttempt") or 1), len(write_indexes) + 1
                    ),
                ),
            },
            reason=(
                "Revise the page using the complete checker observation."
                if write_indexes
                else "Author the page from its Blueprint with editable semantic objects."
            ),
        )
    if expected_stage == "executor" and pnn == "P01" and (
        not gate_indexes or gate_indexes[-1] < write_indexes[-1]
    ):
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


def _fit_size(value: str, width: float, maximum: float, minimum: float = 8) -> float:
    units = sum(
        1.0 if unicodedata.east_asian_width(character) in {"W", "F"} else 0.56
        for character in value
        if character not in "\r\n"
    )
    if units <= 0:
        return maximum
    return round(max(minimum, min(maximum, width * 0.9 / units)), 1)


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
) -> dict[str, Any]:
    return {
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
    return [
        _text_node(
            f"{prefix}-{index + 1}",
            value,
            x=x,
            y=y + index * slot,
            width=width,
            height=slot,
            size=_fit_size(value, width, maximum_size),
            weight=weight,
            color=color,
        )
        for index, value in enumerate(rendered)
        if value
    ]


def _scene_graph(context: dict[str, Any], *, revision: int) -> dict[str, Any]:
    page = context["page"]
    slide = context["slide"]
    title = _wrapped(str(slide["title"]), 28)
    body = [str(value) for value in slide.get("body") or []]
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
            "page-title",
            title,
            x=72,
            y=76,
            width=1136,
            height=106,
            size=38 if role != "cover" else 46,
            weight=700,
            color="#0F172A",
        ),
    ]
    chart = page.get("chartSpec")
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
                        "chartType": chart["chartType"],
                        "values": chart["values"],
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
        right = body[1] if len(body) > 1 else str(page["audienceMove"])
        nodes.extend(
            [
                _shape_node(
                    "left-panel", x=72, y=220, width=536, height=380, fill="#FFFFFF"
                ),
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
                    left,
                    x=112,
                    y=270,
                    width=456,
                    height=250,
                    size=_fit_size(left, 456, 25),
                    weight=600,
                ),
                _text_node(
                    "right-copy",
                    right,
                    x=680,
                    y=270,
                    width=488,
                    height=250,
                    size=_fit_size(right, 488, 25),
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
        statements = body or [str(page["assertion"])]
        for index, statement in enumerate((statements * 3)[:3]):
            x = 120 + index * 370
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
                        statement,
                        x=x,
                        y=470,
                        width=300,
                        height=120,
                        size=_fit_size(statement, 300, 18),
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
            f"Approved evidence · blueprint {context['blueprintSha256'][:12]}",
            x=72,
            y=666,
            width=600,
            height=24,
            size=15,
            color="#64748B",
        )
    )
    return {
        "schemaVersion": 1,
        "workflowRunId": context["workflowRunId"],
        "slideId": page["slideId"],
        "pnn": page["pnn"],
        "pageBlueprintSha256": context["blueprintSha256"],
        "authorAttempt": context["authorAttempt"],
        "background": "#F8FAFC",
        "nodes": nodes,
    }
