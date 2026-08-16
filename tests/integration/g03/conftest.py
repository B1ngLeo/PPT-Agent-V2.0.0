from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from instant_ppt_api.main import create_app
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from .helpers import MemoryObjectStore


@pytest.fixture(scope="session")
def database_url() -> str:
    value = os.environ.get("G03_TEST_DATABASE_URL")
    if not value:
        pytest.fail("G03_TEST_DATABASE_URL is required; use pnpm verify:integration")
    return value


@pytest.fixture(scope="session")
def redis_events_url() -> str:
    return os.environ.get("G03_TEST_REDIS_EVENTS_URL", "redis://localhost:6379/12")


@pytest.fixture(scope="session")
def celery_broker_url() -> str:
    return os.environ.get("G03_TEST_CELERY_BROKER_URL", "redis://localhost:6379/13")


@pytest.fixture(scope="session")
def session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_domain_engine(database_url)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_g03_state(
    session_factory: sessionmaker[Session], redis_events_url: str, celery_broker_url: str
) -> None:
    table_names = (
        "artifact_download_grants",
        "audit_logs",
        "usage_ledger",
        "artifacts",
        "entitlements",
        "memberships",
        "idempotency_records",
        "outbox_events",
        "job_events",
        "published_fixture_manifests",
        "usage_reservations",
        "generation_job_slides",
        "generation_jobs",
        "generation_snapshots",
        "service_actors",
        "organizations",
        "users",
    )
    with session_factory.begin() as session:
        session.execute(text(f"TRUNCATE TABLE {', '.join(table_names)} CASCADE"))
    Redis.from_url(redis_events_url).flushdb()
    Redis.from_url(celery_broker_url).flushdb()


@pytest.fixture
def memory_store() -> MemoryObjectStore:
    return MemoryObjectStore()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    database_url: str,
    redis_events_url: str,
    celery_broker_url: str,
    memory_store: MemoryObjectStore,
) -> TestClient:
    settings = DomainSettings(
        database_url=database_url,
        redis_events_url=redis_events_url,
        celery_broker_url=celery_broker_url,
        sse_heartbeat_seconds=0.1,
        outbox_poll_seconds=0.05,
        worker_lease_seconds=30,
        app_environment="test",
        auth_mode="local",
        download_url_ttl_seconds=15,
    )
    with TestClient(
        create_app(
            settings=settings,
            session_factory=session_factory,
            object_store=memory_store,
        )
    ) as test_client:
        yield test_client
