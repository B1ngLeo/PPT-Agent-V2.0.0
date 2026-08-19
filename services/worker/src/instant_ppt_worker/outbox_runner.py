"""Small standalone transactional-outbox polling process."""

from __future__ import annotations

import signal
import time

from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.outbox import (
    dispatch_outbox_batch,
    enqueue_expired_job_recoveries,
)
from redis import Redis

from instant_ppt_worker.celery_app import celery_app

_stopping = False


def _request_stop(*_: object) -> None:
    global _stopping
    _stopping = True


def _publish_task(destination: str, payload: dict, dedupe_key: str) -> None:
    if destination == "instant_ppt.process_source":
        kwargs = {
            "source_id": payload["sourceId"],
            "organization_id": payload["organizationId"],
        }
    else:
        kwargs = {
            "job_id": payload["jobId"],
            "organization_id": payload["organizationId"],
        }
        if "runtimeContractVersion" in payload:
            kwargs["runtime_contract_version"] = payload["runtimeContractVersion"]
    celery_app.send_task(
        destination,
        kwargs=kwargs,
        task_id=dedupe_key,
        retry=True,
        retry_policy={
            "max_retries": 3,
            "interval_start": 0,
            "interval_step": 0.2,
            "interval_max": 1,
        },
    )


def run_once() -> int:
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    redis_client = Redis.from_url(settings.redis_events_url, decode_responses=True)
    try:
        enqueue_expired_job_recoveries(factory)
        return dispatch_outbox_batch(factory, redis_client, _publish_task)
    finally:
        redis_client.close()
        engine.dispose()


def main() -> None:
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    settings = DomainSettings.from_env()
    while not _stopping:
        dispatched = run_once()
        if dispatched == 0:
            time.sleep(settings.outbox_poll_seconds)


if __name__ == "__main__":
    main()
