"""Transactional outbox dispatcher for Redis fanout and Celery publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import GenerationJob, OutboxEvent
from instant_ppt_domain.runtime_contract import (
    PROCESS_GENERATION_TASK,
    RUNTIME_CONTRACT_VERSION,
)

TaskPublisher = Callable[[str, dict[str, Any], str], None]


def enqueue_expired_job_recoveries(
    session_factory: sessionmaker[Session], *, batch_size: int = 100
) -> int:
    """Reconcile expired PostgreSQL leases into deduplicated recovery tasks.

    Redis/Celery may restore an unacknowledged message as well. Both deliveries are
    safe: the lease token makes reconciliation idempotent and terminal jobs no-op.
    """
    now = datetime.now(UTC)
    created = 0
    with session_factory.begin() as session:
        jobs = session.scalars(
            select(GenerationJob)
            .where(
                GenerationJob.status.in_(("running", "cancel_requested")),
                GenerationJob.lease_expires_at.is_not(None),
                GenerationJob.lease_expires_at <= now,
                GenerationJob.lease_token.is_not(None),
            )
            .order_by(GenerationJob.lease_expires_at, GenerationJob.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            dedupe_key = f"task-recovery:{job.id}:{job.lease_token}"
            exists = session.scalar(
                select(OutboxEvent.id).where(OutboxEvent.dedupe_key == dedupe_key)
            )
            if exists is not None:
                continue
            session.add(
                OutboxEvent(
                    id=new_ulid(),
                    organization_id=job.organization_id,
                    kind="task",
                    aggregate_type="generation_job",
                    aggregate_id=job.id,
                    dedupe_key=dedupe_key,
                    destination=(
                        PROCESS_GENERATION_TASK
                        if job.processor == "real"
                        else "instant_ppt.process_fake_job"
                    ),
                    payload={
                        "jobId": job.id,
                        "organizationId": job.organization_id,
                        "reason": "lease_expired",
                        **(
                            {"runtimeContractVersion": RUNTIME_CONTRACT_VERSION}
                            if job.processor == "real"
                            else {}
                        ),
                    },
                    status="pending",
                    available_at=now,
                )
            )
            created += 1
    return created


def dispatch_outbox_batch(
    session_factory: sessionmaker[Session],
    redis_client: Redis,
    task_publisher: TaskPublisher,
    *,
    batch_size: int = 100,
) -> int:
    """Dispatch pending rows; duplicates are tolerated and deduplicated downstream."""
    dispatched = 0
    for _ in range(batch_size):
        with session_factory.begin() as session:
            row = session.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "pending",
                    OutboxEvent.available_at <= datetime.now(UTC),
                )
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                break
            row.attempts += 1
            try:
                if row.kind == "event":
                    redis_client.publish(row.destination, _canonical_json(row.payload))
                else:
                    task_publisher(row.destination, row.payload, row.dedupe_key)
            except Exception as error:
                row.last_error = f"{type(error).__name__}: {error}"[:2000]
                break
            row.status = "dispatched"
            row.dispatched_at = datetime.now(UTC)
            row.last_error = None
            dispatched += 1
    return dispatched


def _canonical_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
