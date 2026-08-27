"""Pure lifecycle rules shared by HTTP and worker transactions."""

from __future__ import annotations

from instant_ppt_domain.models import TERMINAL_JOB_STATUSES, TERMINAL_WORKFLOW_STATUSES

JOB_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancel_requested"}),
    "running": frozenset({"cancel_requested", "succeeded", "partially_succeeded", "failed"}),
    "cancel_requested": frozenset({"cancelled"}),
    "cancelled": frozenset(),
    "succeeded": frozenset(),
    "partially_succeeded": frozenset(),
    "failed": frozenset(),
}

SLIDE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"ready", "failed", "cancelled"}),
    "ready": frozenset(),
    "failed": frozenset({"retrying"}),
    "retrying": frozenset({"running", "cancelled"}),
    "cancelled": frozenset(),
}

WORKFLOW_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"running", "cancelled"}),
    "running": frozenset(
        {
            "awaiting_stage1_confirmation",
            "template_handoff_ready",
            "awaiting_stage2_confirmation",
            "awaiting_design_confirmation",
            "design_confirmed",
            "final_confirmed",
            "awaiting_refine_spec_approval",
            "needs_manual",
            "partially_succeeded",
            "succeeded",
            "failed",
            "cancel_requested",
        }
    ),
    "awaiting_stage1_confirmation": frozenset({"running", "failed", "cancel_requested"}),
    "template_handoff_ready": frozenset({"running", "failed", "cancel_requested"}),
    "awaiting_stage2_confirmation": frozenset({"running", "failed", "cancel_requested"}),
    "awaiting_design_confirmation": frozenset(
        {"running", "design_confirmed", "failed", "cancel_requested"}
    ),
    "design_confirmed": frozenset({"running", "failed", "cancel_requested"}),
    "final_confirmed": frozenset(
        {"running", "awaiting_refine_spec_approval", "failed", "cancel_requested"}
    ),
    "awaiting_refine_spec_approval": frozenset({"running", "failed", "cancel_requested"}),
    "needs_manual": frozenset({"running", "failed", "cancel_requested"}),
    "cancel_requested": frozenset({"cancelled"}),
    "partially_succeeded": frozenset(),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


class InvalidTransition(ValueError):
    def __init__(self, aggregate: str, current: str, target: str) -> None:
        super().__init__(f"illegal {aggregate} transition: {current} -> {target}")
        self.aggregate = aggregate
        self.current = current
        self.target = target


def validate_job_transition(current: str, target: str) -> None:
    if current == target:
        return
    if target not in JOB_TRANSITIONS[current]:
        raise InvalidTransition("generation_job", current, target)


def validate_slide_transition(current: str, target: str) -> None:
    if current == target:
        return
    if target not in SLIDE_TRANSITIONS[current]:
        raise InvalidTransition("generation_job_slide", current, target)


def validate_workflow_transition(current: str, target: str) -> None:
    if current == target:
        return
    if target not in WORKFLOW_TRANSITIONS[current]:
        raise InvalidTransition("workflow_run", current, target)


def is_terminal_job(status: str) -> bool:
    return status in TERMINAL_JOB_STATUSES


def is_terminal_workflow(status: str) -> bool:
    return status in TERMINAL_WORKFLOW_STATUSES
