"""Bounded subprocess supervision for long-running Default Agentic workflows."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from instant_ppt_worker.errors import RENDER_FAILED, AdapterError
from instant_ppt_worker.models import AdapterResponse
from instant_ppt_worker.workflow_models import GeneratePptxDefaultRequest


class WorkflowCancelled(RuntimeError):
    """The user won the race and the supervised process tree was stopped."""


@dataclass(frozen=True, slots=True)
class SupervisedWorkflowResult:
    response: AdapterResponse
    project: Path
    stdout: str
    stderr: str


_SAFE_ENVIRONMENT = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
)
_SCOPED_IMAGE_ENVIRONMENT = frozenset(
    {
        "OPENAI_API_KEY",
        "IMAGE_GENERATION_ENABLED",
        "IMAGE_BACKEND",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_OUTPUT_FORMAT",
        "OPENAI_IMAGE_SIZE",
        "OPENAI_IMAGE_QUALITY",
        "IMAGE_MAX_PER_DECK",
        "IMAGE_COST_MICROUNITS",
        "OPENAI_IMAGE_TIMEOUT_SECONDS",
    }
)


def minimal_subprocess_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    values = source or dict(os.environ)
    environment = {name: values[name] for name in _SAFE_ENVIRONMENT if values.get(name)}
    environment.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return environment


def _stop_process_tree(process: subprocess.Popen[str], *, grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as error:
        raise AdapterError(
            RENDER_FAILED, "workflow process tree could not be terminated"
        ) from error


def run_default_workflow_supervised(
    root: Path,
    request: GeneratePptxDefaultRequest,
    *,
    hard_timeout_seconds: int,
    cancellation_requested: Callable[[], bool],
    heartbeat: Callable[[], None],
    image_environment: dict[str, str] | None = None,
    poll_seconds: float = 0.25,
    termination_grace_seconds: float = 5.0,
) -> SupervisedWorkflowResult:
    workspace = root.resolve()
    if not workspace.is_dir():
        raise AdapterError(RENDER_FAILED, "workflow workspace does not exist")
    unexpected_image_keys = set(image_environment or {}) - _SCOPED_IMAGE_ENVIRONMENT
    if unexpected_image_keys:
        raise AdapterError(RENDER_FAILED, "image subprocess environment contains unsafe keys")
    request_path = workspace / "workflow-request.json"
    request_path.write_text(
        request.model_dump_json(by_alias=True, indent=2),
        encoding="utf-8",
    )
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    child_environment = minimal_subprocess_environment()
    child_environment.update(
        {
            key: value
            for key, value in (image_environment or {}).items()
            if key in _SCOPED_IMAGE_ENVIRONMENT and value
        }
    )
    # Do not leave stdout/stderr as unread PIPEs while polling.  A successful
    # multi-page adapter can fill an OS pipe before exit, causing parent and
    # child to wait forever even though workflow-result.json is complete.
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err,
    ):
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "instant_ppt_worker.adapter",
                "--request",
                str(request_path),
            ],
            cwd=workspace,
            env=child_environment,
            stdout=out,
            stderr=err,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        deadline = time.monotonic() + hard_timeout_seconds
        next_heartbeat = time.monotonic()
        try:
            while process.poll() is None:
                now = time.monotonic()
                if cancellation_requested():
                    _stop_process_tree(process, grace_seconds=termination_grace_seconds)
                    raise WorkflowCancelled("workflow cancellation requested")
                if now >= deadline:
                    _stop_process_tree(process, grace_seconds=termination_grace_seconds)
                    raise AdapterError(RENDER_FAILED, "workflow hard timeout exceeded")
                if now >= next_heartbeat:
                    heartbeat()
                    next_heartbeat = now + 5.0
                time.sleep(poll_seconds)
            process.wait(timeout=5)
            out.flush()
            err.flush()
            out.seek(0)
            err.seek(0)
            stdout = out.read()
            stderr = err.read()
        except BaseException:
            _stop_process_tree(process, grace_seconds=termination_grace_seconds)
            raise
    try:
        response = AdapterResponse.model_validate(json.loads(stdout))
    except (json.JSONDecodeError, ValueError) as error:
        raise AdapterError(
            RENDER_FAILED,
            f"workflow adapter emitted an invalid response: {stderr[-1000:]}",
        ) from error
    if process.returncode != 0 or response.status != "succeeded":
        detail = response.error.message if response.error else stderr[-1000:]
        code = response.error.code if response.error else RENDER_FAILED
        raise AdapterError(code, detail or "workflow adapter failed")
    project_root = workspace / request.output_key
    candidates = sorted(project_root.parent.glob(f"{project_root.name}_ppt169_????????"))
    project = (
        project_root
        if project_root.is_dir()
        else (candidates[-1] if len(candidates) == 1 else None)
    )
    if project is None or not project.is_dir() or workspace not in project.resolve().parents:
        raise AdapterError(RENDER_FAILED, "workflow adapter did not create the expected project")
    return SupervisedWorkflowResult(
        response=response, project=project, stdout=stdout, stderr=stderr
    )
