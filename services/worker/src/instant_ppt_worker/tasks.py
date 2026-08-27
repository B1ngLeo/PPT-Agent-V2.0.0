"""Celery task wrappers around idempotent domain operations."""

from __future__ import annotations

import os
import random

from celery import Task
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.fake_worker import InjectedWorkerCrash, process_fake_job
from instant_ppt_domain.reconciliation import reconcile_organization_objects
from instant_ppt_domain.runtime_contract import (
    PROCESS_EXPORT_TASK,
    PROCESS_GENERATION_TASK,
    PROCESS_PLANNING_TASK,
    PROCESS_SLIDE_REGENERATION_TASK,
    assert_runtime_contract,
)
from instant_ppt_domain.service import LeaseConflict, ResourceNotFound, SlideStart
from sqlalchemy.exc import OperationalError

from instant_ppt_worker.celery_app import celery_app
from instant_ppt_worker.errors import AdapterError
from instant_ppt_worker.generation_pipeline import (
    InjectedGenerationCrash,
    process_generation_job,
)
from instant_ppt_worker.observability import ObservedTask
from instant_ppt_worker.planning_pipeline import (
    RetryablePlanningFailure,
    process_planning_job,
)
from instant_ppt_worker.presentation_pipeline import (
    process_export,
    process_project_cleanup,
    process_slide_regeneration,
)
from instant_ppt_worker.source_pipeline import (
    ScannerUnavailable,
    SourceObjectError,
    WorkerObjectSettings,
    WorkerObjectStore,
    process_source_pipeline,
)

GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS = int(
    os.getenv("GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS", "7800")
)
GENERATION_TASK_TIME_LIMIT_SECONDS = int(
    os.getenv("GENERATION_TASK_TIME_LIMIT_SECONDS", "8100")
)
if GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS <= 7500:
    raise RuntimeError(
        "GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS must exceed the workflow hard timeout"
    )
if GENERATION_TASK_TIME_LIMIT_SECONDS <= GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS:
    raise RuntimeError(
        "GENERATION_TASK_TIME_LIMIT_SECONDS must exceed the task soft time limit"
    )


def _kill_process(_: SlideStart) -> None:
    os._exit(86)


@celery_app.task(
    bind=True,
    base=ObservedTask,
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
    base=ObservedTask,
    name=PROCESS_GENERATION_TASK,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=4,
    soft_time_limit=GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS,
    time_limit=GENERATION_TASK_TIME_LIMIT_SECONDS,
)
def process_generation_job_task(
    self: Task,
    job_id: str,
    organization_id: str,
    runtime_contract_version: str,
) -> str:
    assert_runtime_contract(runtime_contract_version)
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    worker_id = str(self.request.id)
    try:
        return process_generation_job(
            factory,
            job_id,
            worker_id,
            organization_id=organization_id,
            lease_seconds=settings.worker_lease_seconds,
            crash_callback=_kill_process,
        )
    except ResourceNotFound:
        return "noop_missing"
    except LeaseConflict as error:
        countdown = min(settings.worker_lease_seconds + 1, 60)
        raise self.retry(exc=error, countdown=countdown, max_retries=2) from error
    except (OperationalError, SourceObjectError) as error:
        countdown = min(2 ** (self.request.retries + 1), 8)
        retry_error = RuntimeError(str(error))
        raise self.retry(exc=retry_error, countdown=countdown, max_retries=2) from error
    except InjectedGenerationCrash:
        raise
    finally:
        engine.dispose()


@celery_app.task(
    bind=True,
    base=ObservedTask,
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


@celery_app.task(
    bind=True,
    base=ObservedTask,
    name=PROCESS_PLANNING_TASK,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    soft_time_limit=3900,
    time_limit=4200,
)
def process_planning_job_task(
    self: Task,
    job_id: str,
    organization_id: str,
    runtime_contract_version: str,
) -> str:
    assert_runtime_contract(runtime_contract_version)
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        return process_planning_job(factory, job_id, organization_id)
    except RetryablePlanningFailure as error:
        ceiling = min(2 ** (self.request.retries + 2), 60)
        countdown = random.uniform(1, ceiling)
        raise self.retry(exc=error, countdown=countdown, max_retries=2) from error
    except OperationalError as error:
        ceiling = min(2 ** (self.request.retries + 2), 30)
        countdown = random.uniform(1, ceiling)
        raise self.retry(exc=error, countdown=countdown, max_retries=2) from error
    finally:
        engine.dispose()


@celery_app.task(
    bind=True,
    base=ObservedTask,
    name=PROCESS_SLIDE_REGENERATION_TASK,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    soft_time_limit=180,
    time_limit=210,
)
def process_slide_regeneration_task(
    self: Task,
    job_id: str,
    organization_id: str,
    runtime_contract_version: str,
) -> str:
    assert_runtime_contract(runtime_contract_version)
    del self
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        return process_slide_regeneration(factory, job_id, organization_id)
    finally:
        engine.dispose()


@celery_app.task(
    bind=True,
    base=ObservedTask,
    name=PROCESS_EXPORT_TASK,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    soft_time_limit=600,
    time_limit=660,
)
def process_export_task(
    self: Task,
    job_id: str,
    organization_id: str,
    runtime_contract_version: str,
) -> str:
    assert_runtime_contract(runtime_contract_version)
    del self
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        return process_export(factory, job_id, organization_id)
    finally:
        engine.dispose()


@celery_app.task(
    bind=True,
    base=ObservedTask,
    name="instant_ppt.process_project_cleanup",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    soft_time_limit=180,
    time_limit=210,
)
def process_project_cleanup_task(self: Task, job_id: str, organization_id: str) -> str:
    del self
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        return process_project_cleanup(factory, job_id, organization_id)
    finally:
        engine.dispose()


@celery_app.task(
    bind=True,
    base=ObservedTask,
    name="instant_ppt.reconcile_objects",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    soft_time_limit=300,
    time_limit=330,
)
def reconcile_objects_task(self: Task, organization_id: str) -> dict[str, object]:
    del self
    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        return reconcile_organization_objects(
            factory,
            WorkerObjectStore(WorkerObjectSettings.from_env()),
            organization_id,
        )
    finally:
        engine.dispose()
