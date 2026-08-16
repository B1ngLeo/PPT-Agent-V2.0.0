from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.reconciliation import StoredObject
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


class ReconciliationStore:
    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.failed_removals: set[str] = set()

    def add(self, object_key: str, *, modified_at: datetime | None = None) -> None:
        self.objects[object_key] = StoredObject(
            object_key=object_key,
            last_modified=modified_at or datetime.now(UTC),
        )

    def list_objects(self, prefix: str) -> list[StoredObject]:
        return [value for key, value in self.objects.items() if key.startswith(prefix)]

    def remove(self, object_key: str) -> None:
        if object_key in self.failed_removals:
            raise OSError("injected object deletion failure")
        self.objects.pop(object_key, None)


@pytest.fixture(scope="session")
def database_url() -> str:
    value = os.environ.get("G08_TEST_DATABASE_URL")
    if not value:
        pytest.fail("G08_TEST_DATABASE_URL is required; use pnpm verify:integration:g08")
    return value


@pytest.fixture(scope="session")
def session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_domain_engine(database_url)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_g08_state(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        session.execute(text("TRUNCATE TABLE organizations, users, templates CASCADE"))


@pytest.fixture
def object_store() -> ReconciliationStore:
    return ReconciliationStore()
