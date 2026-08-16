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
from instant_ppt_worker.errors import AdapterError
from instant_ppt_worker.source_pipeline import (
    ScannerUnavailable,
    SourceObjectError,
    process_source_pipeline,
)


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


@celery_app.task(
    bind=True,
    base=Task,
    name="instant_ppt.process_source",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    soft_time_limit=150,
    time_limit=180,
)
def process_source_task(self: Task, source_id: str, organization_id: str) -> str:
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        return process_source_pipeline(factory, source_id, organization_id)
    except (ScannerUnavailable, SourceObjectError, OperationalError, AdapterError) as error:
        countdown = min(2 ** (self.request.retries + 1), 8)
        retry_error = RuntimeError(str(error))
        raise self.retry(exc=retry_error, countdown=countdown, max_retries=2) from error
    finally:
        engine.dispose()
