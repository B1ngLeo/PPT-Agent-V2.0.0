"""Environment-backed runtime configuration with local-only defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@localhost:5432/instant_ppt"
)
DEFAULT_REDIS_EVENTS_URL = "redis://localhost:6379/0"
DEFAULT_CELERY_BROKER_URL = "redis://localhost:6379/1"


@dataclass(frozen=True, slots=True)
class DomainSettings:
    database_url: str
    redis_events_url: str
    celery_broker_url: str
    sse_heartbeat_seconds: float
    outbox_poll_seconds: float
    worker_lease_seconds: int

    @classmethod
    def from_env(cls) -> DomainSettings:
        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            redis_events_url=os.getenv("REDIS_EVENTS_URL", DEFAULT_REDIS_EVENTS_URL),
            celery_broker_url=os.getenv("CELERY_BROKER_URL", DEFAULT_CELERY_BROKER_URL),
            sse_heartbeat_seconds=float(os.getenv("SSE_HEARTBEAT_SECONDS", "20")),
            outbox_poll_seconds=float(os.getenv("OUTBOX_POLL_SECONDS", "0.25")),
            worker_lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "30")),
        )
