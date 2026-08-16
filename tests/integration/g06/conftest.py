from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from instant_ppt_api.main import create_app
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="session")
def database_url() -> str:
    value = os.environ.get("G06_TEST_DATABASE_URL")
    if not value:
        pytest.fail("G06_TEST_DATABASE_URL is required; use pnpm verify:integration:g06")
    return value


@pytest.fixture(scope="session")
def session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_domain_engine(database_url)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_g06_state(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        session.execute(text("TRUNCATE TABLE organizations, users, templates CASCADE"))


@pytest.fixture
def client(session_factory: sessionmaker[Session], database_url: str) -> TestClient:
    settings = DomainSettings(
        database_url=database_url,
        redis_events_url="redis://localhost:6379/14",
        celery_broker_url="redis://localhost:6379/15",
        sse_heartbeat_seconds=0.1,
        outbox_poll_seconds=0.05,
        worker_lease_seconds=30,
        app_environment="test",
        auth_mode="local",
    )
    with TestClient(create_app(settings=settings, session_factory=session_factory)) as test_client:
        yield test_client
