"""Pure lifecycle rules shared by HTTP and worker transactions."""

from __future__ import annotations

from instant_ppt_domain.models import TERMINAL_JOB_STATUSES

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


def is_terminal_job(status: str) -> bool:
    return status in TERMINAL_JOB_STATUSES
