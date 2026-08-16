from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from instant_ppt_domain.service import SYNTHETIC_ORGANIZATION_ID, get_job
from sqlalchemy.orm import Session, sessionmaker

from .helpers import create_job


def _start_worker(environment: dict[str, str]) -> subprocess.Popen:
    output = None if environment.get("G02_DEBUG_PROCESSES") == "1" else subprocess.DEVNULL
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "instant_ppt_worker.celery_app:celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            (
                "--loglevel=INFO"
                if environment.get("G02_DEBUG_PROCESSES") == "1"
                else "--loglevel=WARNING"
            ),
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
        ],
        env=environment,
        stdout=output,
        stderr=output,
    )


def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.mark.skipif(
    os.environ.get("G02_RUN_CELERY_KILL") != "1",
    reason="enabled by the stable G02 integration runner",
)
@pytest.mark.parametrize("iteration", range(10))
def test_actual_celery_worker_kill_recovery(
    session_factory: sessionmaker[Session],
    database_url: str,
    redis_events_url: str,
    celery_broker_url: str,
    iteration: int,
) -> None:
    job_id = create_job(
        session_factory,
        key=f"celery-kill-{iteration}",
        slide_count=2,
        crash_once_at_position=1,
    )
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "REDIS_EVENTS_URL": redis_events_url,
            "CELERY_BROKER_URL": celery_broker_url,
            "CELERY_VISIBILITY_TIMEOUT_SECONDS": "3",
                "WORKER_LEASE_SECONDS": "3",
            "OUTBOX_POLL_SECONDS": "0.05",
        }
    )
    outbox = subprocess.Popen(
        [sys.executable, "-m", "instant_ppt_worker.outbox_runner"],
        env=environment,
        stdout=(
            None
            if environment.get("G02_DEBUG_PROCESSES") == "1"
            else subprocess.DEVNULL
        ),
        stderr=(
            None
            if environment.get("G02_DEBUG_PROCESSES") == "1"
            else subprocess.DEVNULL
        ),
    )
    first_worker: subprocess.Popen | None = None
    second_worker: subprocess.Popen | None = None
    try:
        first_worker = _start_worker(environment)
        exit_code = first_worker.wait(timeout=20)
        assert exit_code == 86
        time.sleep(4)
        second_worker = _start_worker(environment)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            with session_factory() as session:
                status = get_job(session, job_id, SYNTHETIC_ORGANIZATION_ID).status
            if status == "succeeded":
                break
            time.sleep(0.25)
        assert status == "succeeded"
    finally:
        _stop(first_worker)
        _stop(second_worker)
        _stop(outbox)
