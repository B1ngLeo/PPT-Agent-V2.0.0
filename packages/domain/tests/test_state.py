import pytest
from instant_ppt_domain.state import (
    InvalidTransition,
    is_terminal_job,
    validate_job_transition,
    validate_slide_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("queued", "running"),
        ("running", "cancel_requested"),
        ("cancel_requested", "cancelled"),
        ("running", "partially_succeeded"),
    ],
)
def test_legal_job_transitions(current: str, target: str) -> None:
    validate_job_transition(current, target)


def test_terminal_job_cannot_reopen() -> None:
    with pytest.raises(InvalidTransition):
        validate_job_transition("succeeded", "running")


def test_failed_slide_can_retry_but_ready_slide_cannot() -> None:
    validate_slide_transition("failed", "retrying")
    with pytest.raises(InvalidTransition):
        validate_slide_transition("ready", "retrying")


def test_terminal_classification() -> None:
    assert is_terminal_job("succeeded")
    assert is_terminal_job("partially_succeeded")
    assert is_terminal_job("failed")
    assert is_terminal_job("cancelled")
    assert not is_terminal_job("cancel_requested")
