from __future__ import annotations

import hashlib
import os
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from instant_ppt_api.main import create_app
from instant_ppt_domain.artifacts import ArtifactUnavailable, ObjectStat
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


class MemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, object_key: str, payload: bytes, media_type: str) -> None:
        del media_type
        self.objects[object_key] = payload

    def put_file(self, object_key: str, path: Path, media_type: str) -> None:
        self.put_bytes(object_key, path.read_bytes(), media_type)

    def download(self, object_key: str, target: Path, *, max_bytes: int) -> str:
        try:
            payload = self.objects[object_key]
        except KeyError as error:
            raise ArtifactUnavailable("object missing") from error
        if len(payload) > max_bytes:
            raise ArtifactUnavailable("object exceeds download limit")
        target.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def remove(self, object_key: str) -> None:
        self.objects.pop(object_key, None)

    def stat(self, object_key: str) -> ObjectStat:
        try:
            payload = self.objects[object_key]
        except KeyError as error:
            raise ArtifactUnavailable("object missing") from error
        return ObjectStat(size_bytes=len(payload), etag=hashlib.md5(payload).hexdigest())  # noqa: S324

    def presign_get(self, object_key: str, *, expires: timedelta) -> str:
        del expires
        if object_key not in self.objects:
            raise ArtifactUnavailable("object missing")
        return f"https://objects.local/{object_key}?signature=test"


@pytest.fixture(scope="session")
def database_url() -> str:
    value = os.environ.get("G07_TEST_DATABASE_URL")
    if not value:
        pytest.fail("G07_TEST_DATABASE_URL is required; use pnpm verify:integration:g07")
    return value


@pytest.fixture(scope="session")
def session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_domain_engine(database_url)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_g07_state(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        session.execute(text("TRUNCATE TABLE organizations, users, templates CASCADE"))


@pytest.fixture
def object_store() -> MemoryObjectStore:
    return MemoryObjectStore()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    database_url: str,
    object_store: MemoryObjectStore,
) -> TestClient:
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
    with TestClient(
        create_app(
            settings=settings,
            session_factory=session_factory,
            object_store=object_store,
        )
    ) as test_client:
        yield test_client
