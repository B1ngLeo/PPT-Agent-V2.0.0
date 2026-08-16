"""Celery configuration for durable G02 task execution."""

from __future__ import annotations

import os

from celery import Celery
from instant_ppt_domain.config import DomainSettings

settings = DomainSettings.from_env()
celery_app = Celery(
    "instant-ppt-worker",
    broker=settings.celery_broker_url,
    include=["instant_ppt_worker.tasks"],
)
visibility_timeout = int(os.getenv("CELERY_VISIBILITY_TIMEOUT_SECONDS", "30"))
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=False,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    # Celery's Redis transport requires both the transport option and the
    # application-level value. Keeping them aligned makes late-ack recovery
    # deterministic after an abrupt worker exit.
    visibility_timeout=visibility_timeout,
    broker_transport_options={"visibility_timeout": visibility_timeout},
    task_serializer="json",
    accept_content=["json"],
    enable_utc=True,
    timezone="UTC",
)
