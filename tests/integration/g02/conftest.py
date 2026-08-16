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


@pytest.fixture(scope="session")
def database_url() -> str:
    value = os.environ.get("G02_TEST_DATABASE_URL")
    if not value:
        pytest.fail("G02_TEST_DATABASE_URL is required; use pnpm verify:integration")
    return value


@pytest.fixture(scope="session")
def redis_events_url() -> str:
    return os.environ.get("G02_TEST_REDIS_EVENTS_URL", "redis://localhost:6379/14")


@pytest.fixture(scope="session")
def celery_broker_url() -> str:
    return os.environ.get("G02_TEST_CELERY_BROKER_URL", "redis://localhost:6379/15")


@pytest.fixture(scope="session")
def session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_domain_engine(database_url)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_g02_state(
    session_factory: sessionmaker[Session], redis_events_url: str, celery_broker_url: str
) -> None:
    table_names = (
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
    )
    with session_factory.begin() as session:
        session.execute(text(f"TRUNCATE TABLE {', '.join(table_names)} CASCADE"))
    Redis.from_url(redis_events_url).flushdb()
    Redis.from_url(celery_broker_url).flushdb()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    database_url: str,
    redis_events_url: str,
    celery_broker_url: str,
) -> TestClient:
    settings = DomainSettings(
        database_url=database_url,
        redis_events_url=redis_events_url,
        celery_broker_url=celery_broker_url,
        sse_heartbeat_seconds=0.1,
        outbox_poll_seconds=0.05,
        worker_lease_seconds=30,
    )
    with TestClient(create_app(settings=settings, session_factory=session_factory)) as test_client:
        yield test_client
