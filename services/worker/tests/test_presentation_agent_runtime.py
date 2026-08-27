import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from instant_ppt_worker.presentation_agent_runtime import (
    AgentDecision,
    AgentRuntimeError,
    MainPresentationAgent,
)
from instant_ppt_worker.presentation_agent_tools import (
    PresentationAgentToolRegistry,
    ToolCallbacks,
)
from instant_ppt_worker.providers import DeterministicFakeProvider, TextCompletion

from .test_presentation_agent_tools import _context


def _decision(
    *,
    action: str,
    tool: str | None = None,
    arguments: dict[str, Any] | None = None,
    reason: str = "advance the approved presentation phase",
    termination: str | None = None,
    role: str = "executor",
) -> str:
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "role": role,
        "action": action,
        "reason": reason,
    }
    if tool is not None:
        payload["toolName"] = tool
        payload["arguments"] = arguments or {}
    if termination is not None:
        payload["terminationReason"] = termination
    return json.dumps(payload, ensure_ascii=False)


def _svg(font_size: int, suffix: str) -> str:
    del font_size
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720" data-pptx-page-role="cover">'
        '<rect id="agent-background" x="0" y="0" width="1280" height="720" '
        'fill="#F8FAFC"/>'
        f'<text id="page-title" data-test-revision="{suffix}" x="72" y="120" '
        f'font-size="64" '
        'fill="#0F172A">私有模型公告解读</text>'
        '<text id="page-number" x="1208" y="680" text-anchor="end">P01</text>'
        "</svg>"
    )


def _locked(context: Any) -> dict[str, Any]:
    page = next(page for page in context.request.outline if page.pnn == context.current_pnn)
    return {
        "approvedSnapshotSha256": context.request.approval.snapshot_sha256,
        "page": page.model_dump(by_alias=True, mode="json"),
        "untrusted-source-data": [fragment for fragment in context.fragments],
        "specLock": (context.project / "spec_lock.md").read_text(encoding="utf-8"),
    }


def test_model_observes_gate_failure_and_revises_the_authored_svg(tmp_path: Path) -> None:
    gate_calls: list[bool] = []

    def svg_gate(_pnn: str, path: Path, _subject: str) -> dict[str, Any]:
        passed = 'data-test-revision="revised"' in path.read_text(encoding="utf-8")
        gate_calls.append(passed)
        return {
            "passed": passed,
            "findings": [] if passed else [{"code": "TITLE_TOO_SMALL", "severity": "blocking"}],
        }

    context = _context(tmp_path, callbacks=ToolCallbacks(svg_gate=svg_gate))
    provider = DeterministicFakeProvider(
        [
            _decision(action="tool", tool="read_approved_context", arguments={"pnn": "P01"}),
            _decision(
                action="tool",
                tool="write_or_patch_slide_svg",
                arguments={"pnn": "P01", "mode": "direct-svg", "svg": _svg(12, "draft")},
            ),
            _decision(action="tool", tool="run_svg_gate", arguments={"pnn": "P01"}),
            _decision(
                action="tool",
                tool="write_or_patch_slide_svg",
                arguments={"pnn": "P01", "mode": "direct-svg", "svg": _svg(38, "revised")},
                reason="repair TITLE_TOO_SMALL from the actual gate observation",
            ),
            _decision(action="tool", tool="run_svg_gate", arguments={"pnn": "P01"}),
            _decision(action="complete", termination="P01 passed after observed repair"),
        ]
    )
    agent = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    )

    result = agent.run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="Author P01 and repair all checker findings",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "completed"
    assert result.termination_reason == "P01 passed after observed repair"
    assert gate_calls == [False, True]
    assert len(provider.calls) == 6
    assert "TITLE_TOO_SMALL" in json.dumps(provider.calls[3]["messages"], ensure_ascii=False)
    assert 'data-test-revision="revised"' in (
        context.project / "svg_output" / "slide_01.svg"
    ).read_text(encoding="utf-8")
    tool_records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (context.project / "agent" / "tool-calls").glob("*.json")
    ]
    assert all(record["authorTurnId"] for record in tool_records)
    assert all(record["modelVersion"] == context.request.versions.model for record in tool_records)
    assert all(
        record["promptVersion"] == context.request.versions.prompt for record in tool_records
    )
    assert all(
        record["referenceVersion"] == context.request.versions.reference for record in tool_records
    )


def test_phase_cannot_complete_before_supervisor_required_tools(tmp_path: Path) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [
            _decision(action="complete", termination="premature"),
            _decision(
                action="tool",
                tool="read_approved_context",
                arguments={"pnn": "P01"},
            ),
            _decision(action="complete", termination="required evidence observed"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="prove required tool enforcement",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"read_approved_context"}),
    )

    assert result.status == "completed"
    assert result.termination_reason == "required evidence observed"
    assert len(provider.calls) == 3
    assert "AGENT_PHASE_REQUIRED_TOOLS_MISSING" in json.dumps(
        provider.calls[1]["messages"], ensure_ascii=False
    )


def test_phase_cannot_pause_before_supervisor_required_tools(tmp_path: Path) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [
            _decision(action="pause", termination="awaiting-next-turn"),
            _decision(
                action="tool",
                tool="read_approved_context",
                arguments={"pnn": "P01"},
            ),
            _decision(action="complete", termination="required evidence observed"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="reject an early model-selected pause",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"read_approved_context"}),
    )

    assert result.status == "completed"
    assert result.termination_reason == "required evidence observed"
    assert "phase cannot pause before tools" in json.dumps(
        provider.calls[1]["messages"], ensure_ascii=False
    )


def test_turn_budget_is_enforced_before_a_selected_tool_can_mutate(tmp_path: Path) -> None:
    context = _context(tmp_path)
    runtime = context.request.runtime.model_copy(update={"max_turns": 1})
    request = context.request.model_copy(update={"runtime": runtime})
    context = replace(context, request=request)
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="write_or_patch_slide_svg",
                arguments={"pnn": "P01", "mode": "direct-svg", "svg": _svg(38, "blocked")},
            )
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="respect the bounded turn policy",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "paused"
    assert result.termination_reason == "turn-budget-exhausted"
    assert not (context.project / "svg_output" / "slide_01.svg").exists()


class _FixedUsageProvider:
    provider_name = "fixed-usage"

    def __init__(self, *, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.calls = 0

    def complete(
        self,
        _messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        del response_format, max_completion_tokens
        self.calls += 1
        return TextCompletion(
            content=_decision(action="complete", termination="provider completed"),
            model="fixed-usage-v1",
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
        )


class _PreservedThinkingProvider:
    provider_name = "preserved-thinking"
    preserve_thinking_history = True

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        del response_format, max_completion_tokens
        self.calls.append(messages)
        if len(self.calls) == 1:
            content = _decision(
                action="tool",
                tool="read_approved_context",
                arguments={"pnn": "P01"},
            )
            reasoning = "private-reasoning-turn-1"
        else:
            content = _decision(
                action="complete",
                termination="preserved thinking observed",
            )
            reasoning = "private-reasoning-turn-2"
        return TextCompletion(
            content=content,
            model="qwen3.8-max",
            prompt_tokens=10,
            completion_tokens=20,
            reasoning_content=reasoning,
            finish_reason="stop",
        )


def test_agent_forwards_preserved_thinking_on_the_next_model_turn(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        allowed_tools=frozenset({"read_approved_context"}),
    )
    provider = _PreservedThinkingProvider()

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="preserve Qwen thinking across a tool observation",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"read_approved_context"}),
    )

    assert result.status == "completed"
    assistant_history = [
        message for message in provider.calls[1] if message.get("role") == "assistant"
    ]
    assert assistant_history[-1]["reasoning_content"] == "private-reasoning-turn-1"


class _TerminalThinkingProvider:
    provider_name = "terminal-thinking"
    preserve_thinking_history = True

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        del response_format, max_completion_tokens
        self.calls.append(messages)
        turn_number = len(self.calls)
        return TextCompletion(
            content=_decision(
                action="complete",
                termination=f"terminal-turn-{turn_number}",
            ),
            model="qwen3.8-max",
            prompt_tokens=10,
            completion_tokens=20,
            reasoning_content=f"terminal-reasoning-{turn_number}",
            finish_reason="stop",
        )


def test_terminal_assistant_reasoning_is_replayed_in_the_next_phase(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    provider = _TerminalThinkingProvider()
    agent = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    )

    first = agent.run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="complete the first phase",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )
    next_context = replace(context, current_pnn="P02", stage="executor_remaining")
    second = agent.run_phase(
        phase_id="executor_remaining",
        role="executor",
        goal="continue with the next phase",
        locked_context=_locked(next_context),
        tools=PresentationAgentToolRegistry(next_context),
    )

    assert first.status == "completed"
    assert second.status == "completed"
    terminal_messages = [
        message
        for message in provider.calls[1]
        if message.get("reasoning_content") == "terminal-reasoning-1"
    ]
    assert len(terminal_messages) == 1
    assert json.loads(terminal_messages[0]["content"])["terminationReason"] == ("terminal-turn-1")


def test_agent_does_not_compact_preserved_thinking_after_sixteen_messages(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    agent = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=_PreservedThinkingProvider(),
    )
    expected_reasoning: list[str] = []
    for index in range(10):
        reasoning = f"private-reasoning-{index}"
        expected_reasoning.append(reasoning)
        agent.state["messages"].extend(
            [
                {
                    "role": "assistant",
                    "content": f'{{"turn":{index}}}',
                    "reasoningContent": reasoning,
                    "locked": False,
                    "phaseId": "executor_p01",
                },
                {
                    "role": "user",
                    "content": f"tool-observation-{index}",
                    "locked": False,
                    "phaseId": "executor_p01",
                },
            ]
        )

    messages = agent._provider_messages("executor_p01")

    assert [
        message["reasoning_content"] for message in messages if message.get("reasoning_content")
    ] == expected_reasoning
    assert not any(
        "Earlier observations in this phase" in message["content"] for message in messages
    )


def test_preserved_thinking_counts_toward_the_context_limit(tmp_path: Path) -> None:
    context = _context(tmp_path)
    runtime = context.request.runtime.model_copy(update={"max_context_characters": 10_000})
    request = context.request.model_copy(update={"runtime": runtime})
    agent = MainPresentationAgent(
        project=context.project,
        request=request,
        provider=_PreservedThinkingProvider(),
    )
    agent.state["messages"].append(
        {
            "role": "assistant",
            "content": "{}",
            "reasoningContent": "r" * 10_000,
            "locked": False,
            "phaseId": "executor_p01",
        }
    )

    with pytest.raises(AgentRuntimeError, match="preserved thinking"):
        agent._provider_messages("executor_p01")


@pytest.mark.parametrize(
    ("runtime_updates", "tokens", "clock_values", "expected_status", "expected_reason"),
    [
        ({"max_tokens": 100}, (60, 50), (0.0, 0.1), "paused", "token-budget-exhausted"),
        (
            {
                "max_cost_microunits": 10,
                "input_cost_microunits_per_1k": 1000,
                "output_cost_microunits_per_1k": 1000,
            },
            (60, 50),
            (0.0, 0.1),
            "paused",
            "cost-budget-exhausted",
        ),
        (
            {"soft_timeout_seconds": 30, "hard_timeout_seconds": 60},
            (1, 1),
            (0.0, 31.0),
            "paused",
            "soft-timeout",
        ),
        (
            {"soft_timeout_seconds": 30, "hard_timeout_seconds": 60},
            (1, 1),
            (0.0, 61.0),
            "failed",
            "hard-timeout",
        ),
    ],
)
def test_token_cost_and_timeout_budgets_are_supervisor_enforced(
    tmp_path: Path,
    runtime_updates: dict[str, int],
    tokens: tuple[int, int],
    clock_values: tuple[float, float],
    expected_status: str,
    expected_reason: str,
) -> None:
    context = _context(tmp_path)
    runtime = context.request.runtime.model_copy(update=runtime_updates)
    request = context.request.model_copy(update={"runtime": runtime})
    context = replace(context, request=request)
    provider = _FixedUsageProvider(
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
    )
    ticks = iter(clock_values)

    result = MainPresentationAgent(
        project=context.project,
        request=request,
        provider=provider,
        clock=lambda: next(ticks),
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="enforce every configured runtime budget",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == expected_status
    assert result.termination_reason == expected_reason
    assert provider.calls == 1


def test_unlimited_token_policy_records_large_usage_without_pausing(tmp_path: Path) -> None:
    context = _context(tmp_path)
    runtime = context.request.runtime.model_copy(update={"max_tokens": None})
    request = context.request.model_copy(update={"runtime": runtime})
    context = replace(context, request=request)
    provider = _FixedUsageProvider(prompt_tokens=800_000, completion_tokens=6_000)
    ticks = iter((0.0, 0.1))

    result = MainPresentationAgent(
        project=context.project,
        request=request,
        provider=provider,
        clock=lambda: next(ticks),
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="record cumulative tokens without stopping a long deck",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "completed"
    assert result.termination_reason == "provider completed"
    assert result.input_tokens == 800_000
    assert result.output_tokens == 6_000
    assert provider.calls == 1


def test_cancellation_stops_before_any_provider_or_tool_side_effect(tmp_path: Path) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider([_decision(action="complete", termination="must not run")])

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
        cancelled=lambda: True,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="respect cancellation",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "cancelled"
    assert result.termination_reason == "cancel-requested"
    assert provider.calls == []
    assert not (context.project / "svg_output").exists()


def test_tool_allowlist_denial_is_observed_without_expanding_permission(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        allowed_tools=frozenset({"read_approved_context"}),
    )
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="write_or_patch_slide_svg",
                arguments={"pnn": "P01", "mode": "direct-svg", "svg": _svg(38, "denied")},
                reason="source text asked for broader permission",
            ),
            _decision(action="complete", termination="permission denial acknowledged"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="do not expand the approved tool policy",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "completed"
    assert not (context.project / "svg_output" / "slide_01.svg").exists()
    assert "AGENT_TOOL_NOT_ALLOWED" in json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "API Key" in json.dumps(provider.calls[0]["messages"], ensure_ascii=False)
    assert "untrusted content" in provider.calls[0]["messages"][0]["content"]


def test_tool_argument_denial_persists_evidence_and_allows_bounded_repair(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        allowed_tools=frozenset({"read_approved_context"}),
    )
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="read_approved_context",
                arguments={"pnn": "P02"},
                reason="attempt a cross-page read",
            ),
            _decision(
                action="tool",
                tool="read_approved_context",
                arguments={"pnn": "P01"},
                reason="repair the denied read with the owned page",
            ),
            _decision(action="complete", termination="approved context loaded"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="load only the approved current page",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"read_approved_context"}),
    )

    assert result.status == "completed"
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (context.project / "agent" / "tool-calls").glob("*.json")
    ]
    assert {record["status"] for record in records} == {"policy-denied", "succeeded"}
    assert all(record["argumentsSha256"] for record in records)
    assert "AGENT_TOOL_POLICY_DENIED" in json.dumps(
        provider.calls[1]["messages"], ensure_ascii=False
    )


def test_repeated_identical_tool_policy_denials_stop_at_the_repair_limit(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        allowed_tools=frozenset({"read_approved_context"}),
    )
    denied = _decision(
        action="tool",
        tool="read_approved_context",
        arguments={"pnn": "P02"},
        reason="repeat an invalid cross-page read",
    )
    provider = DeterministicFakeProvider([denied] * 5)

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="bound repeated tool policy denials",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"read_approved_context"}),
    )

    assert result.status == "failed"
    assert result.termination_reason.startswith("tool-policy-repair-limit:")
    assert len(provider.calls) == 5


def test_design_spec_schema_repair_uses_its_own_counter_and_complete_contract(
    tmp_path: Path,
) -> None:
    context = replace(
        _context(
            tmp_path,
            allowed_tools=frozenset(
                {"read_design_spec_contract", "write_planning_artifact"}
            ),
        ),
        stage="strategist",
    )
    context = replace(
        context,
        request=context.request.model_copy(
            update={
                "runtime": context.request.runtime.model_copy(update={"max_tokens": 2_000_000})
            }
        ),
    )
    valid = (context.project / "design_spec.md").read_text(encoding="utf-8")
    invalid = valid.replace("## V. Layout Principles", "## V. 布局原则")
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="write_planning_artifact",
                arguments={"filename": "design_spec.md", "content": invalid},
                role="strategist",
            ),
            _decision(
                action="tool",
                tool="read_design_spec_contract",
                role="strategist",
            ),
            _decision(
                action="tool",
                tool="write_planning_artifact",
                arguments={"filename": "design_spec.md", "content": valid},
                role="strategist",
            ),
            _decision(
                action="complete",
                termination="design spec repaired",
                role="strategist",
            ),
        ]
    )
    agent = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    )

    result = agent.run_phase(
        phase_id="strategist",
        role="strategist",
        goal="author the canonical design spec",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset(
            {"read_design_spec_contract", "write_planning_artifact"}
        ),
    )

    assert result.status == "completed", result
    state = json.loads(
        (context.project / "agent" / "runtime-state.json").read_text(encoding="utf-8")
    )
    assert state["phases"]["strategist"]["designSpecRepairCount"] == 1
    assert state["phases"]["strategist"]["toolPolicyDenialCount"] == 0
    assert "DESIGN_SPEC_SCHEMA_INVALID" in json.dumps(
        provider.calls[1]["messages"], ensure_ascii=False
    )
    assert "V. Layout Principles" in json.dumps(
        provider.calls[2]["messages"], ensure_ascii=False
    )


def test_visual_review_contract_exposes_direct_svg_as_the_only_authoring_mode(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path, visual_review_required=True)
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="write_or_patch_slide_svg",
                arguments={"pnn": "P01", "mode": "direct-svg", "svg": _svg(38, "reviewed")},
            ),
            _decision(action="complete", termination="direct SVG authored"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="author P01 for visual review",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"write_or_patch_slide_svg"}),
    )

    assert result.status == "completed"
    initial_contract = provider.calls[0]["messages"][1]["content"]
    assert '"mode":"direct-svg"' in initial_contract
    assert "alternativeMode" not in initial_contract
    assert "direct-svg is the only authoring mode" in initial_contract
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (context.project / "agent" / "tool-calls").glob("*.json")
    ]
    assert {record["status"] for record in records} == {"succeeded"}


def test_direct_svg_repair_contract_remains_direct_svg_only(tmp_path: Path) -> None:
    context = replace(
        _context(tmp_path, visual_review_required=True),
        stage="visual-repair",
        required_authoring_mode="direct-svg",
    )
    current_svg = _svg(34, "current")
    svg_path = context.project / "svg_output" / "slide_01.svg"
    svg_path.parent.mkdir(parents=True)
    svg_path.write_text(current_svg, encoding="utf-8")
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="read_approved_context",
                arguments={"pnn": "P01"},
            ),
            _decision(
                action="tool",
                tool="write_or_patch_slide_svg",
                arguments={"pnn": "P01", "mode": "direct-svg", "svg": _svg(38, "repair")},
            ),
            _decision(action="complete", termination="direct SVG repaired"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="visual-repair-r1-p01",
        role="executor",
        goal="repair P01 without changing its authoring mode",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"read_approved_context", "write_or_patch_slide_svg"}),
    )

    assert result.status == "completed"
    contract = provider.calls[0]["messages"][1]["content"]
    assert "direct-svg is the only authoring mode" in contract
    assert "data-pptx-bounds is exactly x y width height" in contract
    assert "x+width<=1280 and y+height<=720" in contract
    assert "alternativeMode" not in contract
    repair_observation = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "currentAuthoringAsset" in repair_observation
    assert "data-test-revision" in repair_observation
    assert "current" in repair_observation


def test_invalid_structured_output_is_repaired_within_the_bounded_turn_loop(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [
            "not-json",
            _decision(action="complete", termination="schema repaired"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="return a structured decision",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "completed"
    assert len(provider.calls) == 2
    assert '"action":"tool"' in provider.calls[0]["messages"][0]["content"]
    assert "never callTool" in provider.calls[0]["messages"][0]["content"]
    assert (
        '"read_approved_context":{"argumentsExample":{"pnn":"P01"}'
        in (provider.calls[0]["messages"][1]["content"])
    )
    assert "violated AgentDecision v1" in provider.calls[1]["messages"][-1]["content"]
    assert "never use callTool" in provider.calls[1]["messages"][-1]["content"]
    turns = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (context.project / "agent" / "turns").glob("*.json")
    ]
    assert any(turn["status"] == "invalid-structured-output" for turn in turns)


@pytest.mark.parametrize(
    "provider_output",
    [
        """```json
        {"schemaVersion":1,"role":"EXECUTOR","action":"callTool",\
        "toolName":"readApprovedContext","arguments":{"pnn":"P01"},\
        "reason":"load context","terminationReason":"not applicable"}
        ```""",
        json.dumps(
            {
                "decision": {
                    "schemaVersion": 1,
                    "role": "executor",
                    "action": "complete",
                    "toolName": "read_approved_context",
                    "arguments": {"ignored": True},
                    "reason": "provider wrapped the decision",
                }
            }
        ),
    ],
)
def test_provider_json_presentation_variants_are_normalized_without_a_repair_turn(
    tmp_path: Path,
    provider_output: str,
) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [
            provider_output,
            _decision(action="complete", termination="tool loop complete"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="accept provider JSON presentation variants",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "completed"
    expected_calls = 2 if "callTool" in provider_output else 1
    assert len(provider.calls) == expected_calls
    turns = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (context.project / "agent" / "turns").glob("*.json")
    ]
    assert all(turn["status"] != "invalid-structured-output" for turn in turns)


def test_repeated_invalid_structured_output_gets_four_bounded_repairs(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [
            "not-json-1",
            "not-json-2",
            "not-json-3",
            "not-json-4",
            _decision(action="complete", termination="four schema repairs recovered"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="recover from a flaky structured-output proxy",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "completed"
    assert result.termination_reason == "four schema repairs recovered"
    assert len(provider.calls) == 5


def test_premature_fail_after_recoverable_tool_denial_is_bounded_and_retried(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [
            _decision(action="fail", termination="tool arguments can be corrected"),
            _decision(
                action="tool",
                tool="read_approved_context",
                arguments={"pnn": "P01"},
            ),
            _decision(action="complete", termination="required tool recovered"),
        ]
    )

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="recover a correctable tool denial",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
        required_tools=frozenset({"read_approved_context"}),
    )

    assert result.status == "completed"
    assert result.termination_reason == "required tool recovered"
    assert len(provider.calls) == 3
    state = json.loads(
        (context.project / "agent" / "runtime-state.json").read_text(encoding="utf-8")
    )
    assert state["phases"]["executor_p01"]["prematureFailureCount"] == 1


@pytest.mark.parametrize("crash_point", ["after-provider", "after-tool"])
def test_resume_reuses_provider_turn_and_idempotent_tool_call(
    tmp_path: Path,
    crash_point: str,
) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="write_or_patch_slide_svg",
                arguments={"pnn": "P01", "mode": "direct-svg", "svg": _svg(38, "resume")},
            ),
            _decision(action="complete", termination="resumed without duplicate billing"),
        ]
    )
    crashed = False

    def crash(point: str, _payload: dict[str, Any]) -> None:
        nonlocal crashed
        if point == crash_point and not crashed:
            crashed = True
            raise RuntimeError("injected worker kill")

    with pytest.raises(RuntimeError, match="injected worker kill"):
        MainPresentationAgent(
            project=context.project,
            request=context.request,
            provider=provider,
            crash_hook=crash,
        ).run_phase(
            phase_id="executor_p01",
            role="executor",
            goal="resume the same pending author action",
            locked_context=_locked(context),
            tools=PresentationAgentToolRegistry(context),
        )
    assert len(provider.calls) == 1

    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=provider,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="resume the same pending author action",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "completed"
    assert result.resumed is True
    assert len(provider.calls) == 2
    assert len(list((context.project / "agent" / "tool-calls").glob("*.json"))) == 1
    stale = json.loads(
        (context.project / "validation" / "agent-stale.json").read_text(encoding="utf-8")
    )
    assert len(stale["entries"]) == 1


class _CrashDuringProvider:
    provider_name = "crash-provider"
    calls = 0

    def complete(
        self,
        _messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        del response_format, max_completion_tokens
        self.calls += 1
        raise RuntimeError("provider process disappeared")


def test_unknown_provider_outcome_pauses_instead_of_repeating_a_billable_call(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    crashing = _CrashDuringProvider()
    with pytest.raises(RuntimeError, match="provider process disappeared"):
        MainPresentationAgent(
            project=context.project,
            request=context.request,
            provider=crashing,
        ).run_phase(
            phase_id="executor_p01",
            role="executor",
            goal="never duplicate an uncertain provider call",
            locked_context=_locked(context),
            tools=PresentationAgentToolRegistry(context),
        )

    replacement = DeterministicFakeProvider(
        [_decision(action="complete", termination="must not be called")]
    )
    result = MainPresentationAgent(
        project=context.project,
        request=context.request,
        provider=replacement,
    ).run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="never duplicate an uncertain provider call",
        locked_context=_locked(context),
        tools=PresentationAgentToolRegistry(context),
    )

    assert result.status == "paused"
    assert result.termination_reason == "provider-outcome-unknown-no-repeat"
    assert replacement.calls == []


def test_single_agent_session_carries_strategist_observation_into_executor(
    tmp_path: Path,
) -> None:
    base = _context(tmp_path)
    strategist_context = replace(
        base,
        stage="design_spec_gate1",
        current_pnn="P01",
    )
    executor_context = replace(base, stage="executor_p01", current_pnn="P01")
    provider = DeterministicFakeProvider(
        [
            _decision(
                action="tool",
                tool="read_design_catalog",
                role="strategist",
            ),
            _decision(
                action="complete",
                termination="strategy locked",
                role="strategist",
            ),
            _decision(action="tool", tool="read_approved_context", arguments={"pnn": "P01"}),
            _decision(action="complete", termination="executor retained strategy"),
        ]
    )
    agent = MainPresentationAgent(
        project=base.project,
        request=base.request,
        provider=provider,
    )

    strategy = agent.run_phase(
        phase_id="design_spec_gate1",
        role="strategist",
        goal="select semantic design primitives",
        locked_context=_locked(strategist_context),
        tools=PresentationAgentToolRegistry(strategist_context),
    )
    execution = agent.run_phase(
        phase_id="executor_p01",
        role="executor",
        goal="author P01 using the retained strategy",
        locked_context=_locked(executor_context),
        tools=PresentationAgentToolRegistry(executor_context),
    )

    assert strategy.status == execution.status == "completed"
    executor_prompt = json.dumps(provider.calls[2]["messages"], ensure_ascii=False)
    assert "instant-ppt.design-catalog.v1" in executor_prompt
    assert "select semantic design primitives" in executor_prompt
    assert "author P01 using the retained strategy" in executor_prompt


def test_materialized_agent_decision_schema_matches_runtime_contract() -> None:
    path = Path("services/worker/contracts/agent-decision.v1.schema.json")
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    generated = AgentDecision.model_json_schema()
    for key in ("properties", "required", "title", "type"):
        assert on_disk[key] == generated[key]
