import pytest
from instant_ppt_worker.errors import AdapterError
from instant_ppt_worker.workflow_supervisor import (
    _report_progress_safely,
    minimal_subprocess_environment,
    run_default_workflow_supervised,
)


def test_minimal_workflow_environment_drops_credentials_and_forces_utf8() -> None:
    environment = minimal_subprocess_environment(
        {
            "PATH": "C:\\safe-bin",
            "SYSTEMROOT": "C:\\Windows",
            "USERPROFILE": "C:\\Users\\worker",
            "MOONSHOT_API_KEY": "secret-kimi",
            "OPENAI_API_KEY": "secret-image",
            "S3_SECRET_KEY": "secret-storage",
            "DATABASE_URL": "postgresql://secret",
        }
    )

    assert environment["PATH"] == "C:\\safe-bin"
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"
    assert environment["PYTHONHASHSEED"] == "0"
    assert not {
        "MOONSHOT_API_KEY",
        "OPENAI_API_KEY",
        "S3_SECRET_KEY",
        "DATABASE_URL",
    }.intersection(environment)


def test_supervisor_rejects_non_image_scoped_environment_before_launch(tmp_path) -> None:
    with pytest.raises(AdapterError, match="unsafe keys"):
        run_default_workflow_supervised(
            tmp_path,
            object(),
            hard_timeout_seconds=60,
            cancellation_requested=lambda: False,
            heartbeat=lambda: None,
            image_environment={"DATABASE_URL": "must-not-cross-boundary"},
        )


def test_supervisor_rejects_non_text_scoped_environment_before_launch(tmp_path) -> None:
    with pytest.raises(AdapterError, match="unsafe keys"):
        run_default_workflow_supervised(
            tmp_path,
            object(),
            hard_timeout_seconds=60,
            cancellation_requested=lambda: False,
            heartbeat=lambda: None,
            text_environment={"DATABASE_URL": "must-not-cross-boundary"},
        )


def test_progress_observation_failure_does_not_interrupt_generation(tmp_path) -> None:
    attempts = 0

    def failing_progress(_workspace) -> None:
        nonlocal attempts
        attempts += 1
        raise OSError("concurrent event file write")

    _report_progress_safely(failing_progress, tmp_path)

    assert attempts == 1
