"""Deterministic fake worker used to prove orchestration semantics in G02."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_domain.service import (
    SlideStart,
    claim_job,
    complete_slide,
    finalize_job,
    get_job,
    heartbeat_job,
    start_next_slide,
)


class InjectedWorkerCrash(RuntimeError):
    """Raised by in-process tests at the same persisted boundary as a process kill."""


def process_fake_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    worker_id: str,
    *,
    organization_id: str | None = None,
    lease_seconds: int = 30,
    crash_callback: Callable[[SlideStart], None] | None = None,
) -> str:
    """Process one job with a resumable transaction around every slide boundary."""
    if organization_id is not None:
        with session_factory() as session:
            get_job(session, job_id, organization_id)
    with session_factory.begin() as session:
        claimed = claim_job(
            session, job_id, worker_id, lease_seconds=lease_seconds
        )
        if claimed is None:
            return "noop_terminal"

    while True:
        with session_factory.begin() as session:
            heartbeat_job(session, job_id, worker_id, lease_seconds=lease_seconds)
            slide = start_next_slide(session, job_id, worker_id)
        if slide is None:
            with session_factory.begin() as session:
                return finalize_job(session, job_id, worker_id)
        if slide.crash_now:
            if crash_callback is not None:
                crash_callback(slide)
            raise InjectedWorkerCrash(
                f"deterministic crash after starting slide at position {slide.position}"
            )
        if slide.step_delay_ms:
            time.sleep(slide.step_delay_ms / 1000)
        succeeded = slide.failure_mode == "none" or (
            slide.failure_mode == "once" and slide.attempt > 1
        )
        with session_factory.begin() as session:
            complete_slide(
                session,
                job_id,
                slide.slide_id,
                worker_id,
                succeeded=succeeded,
            )
