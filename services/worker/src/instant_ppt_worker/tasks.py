"""Celery task wrappers around idempotent domain operations."""

from __future__ import annotations

import os

from celery import Task
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.fake_worker import InjectedWorkerCrash, process_fake_job
from instant_ppt_domain.service import LeaseConflict, SlideStart
from sqlalchemy.exc import OperationalError

from instant_ppt_worker.celery_app import celery_app


def _kill_process(_: SlideStart) -> None:
    os._exit(86)


@celery_app.task(
    bind=True,
    base=Task,
    name="instant_ppt.process_fake_job",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
)
def process_fake_job_task(self: Task, job_id: str, organization_id: str) -> str:
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    worker_id = str(self.request.id)
    try:
        return process_fake_job(
            factory,
            job_id,
            worker_id,
            organization_id=organization_id,
            lease_seconds=settings.worker_lease_seconds,
            crash_callback=_kill_process,
        )
    except LeaseConflict as error:
        raise self.retry(exc=error, countdown=1, max_retries=2) from error
    except OperationalError as error:
        countdown = min(2 ** (self.request.retries + 1), 8)
        raise self.retry(exc=error, countdown=countdown, max_retries=2) from error
    except InjectedWorkerCrash:
        raise
    finally:
        engine.dispose()
