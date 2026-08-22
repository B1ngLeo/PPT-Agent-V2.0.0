import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from instant_ppt_worker.presentation_agent_runtime import AgentDecision, MainPresentationAgent
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
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
        'viewBox="0 0 1280 720">'
        '<rect id="agent-background" x="0" y="0" width="1280" height="720" '
        'fill="#F8FAFC"/>'
        f'<text id="agent-title-{suffix}" x="72" y="120" font-size="{font_size}" '
        'fill="#0F172A">Agent-authored assertion</text>'
        "</svg>"
    )


def _locked(context: Any) -> dict[str, Any]:
    page = next(page for page in context.blueprint.pages if page.pnn == context.current_pnn)
    return {
        "approvedSnapshotSha256": context.request.approval.snapshot_sha256,
        "pageBlueprintSha256": context.blueprint_sha256,
        "page": page.model_dump(by_alias=True, mode="json"),
        "untrusted-source-data": [fragment for fragment in context.fragments],
        "specLock": (context.project / "spec_lock.md").read_text(encoding="utf-8"),
    }


def test_model_observes_gate_failure_and_revises_the_authored_svg(tmp_path: Path) -> None:
    gate_calls: list[bool] = []

    def svg_gate(_pnn: str, path: Path, _subject: str) -> dict[str, Any]:
        passed = 'font-size="38"' in path.read_text(encoding="utf-8")
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
    assert "agent-title-revised" in (
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
        record["referenceVersion"] == context.request.versions.reference
        for record in tool_records
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


def test_cancellation_stops_before_any_provider_or_tool_side_effect(tmp_path: Path) -> None:
    context = _context(tmp_path)
    provider = DeterministicFakeProvider(
        [_decision(action="complete", termination="must not run")]
    )

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
    assert "AGENT_TOOL_NOT_ALLOWED" in json.dumps(
        provider.calls[1]["messages"], ensure_ascii=False
    )
    assert "API Key" in json.dumps(provider.calls[0]["messages"], ensure_ascii=False)
    assert "untrusted content" in provider.calls[0]["messages"][0]["content"]


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
    assert "violated AgentDecision v1" in provider.calls[1]["messages"][-1]["content"]
    turns = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (context.project / "agent" / "turns").glob("*.json")
    ]
    assert any(turn["status"] == "invalid-structured-output" for turn in turns)


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
