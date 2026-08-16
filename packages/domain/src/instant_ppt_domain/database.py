"""SQLAlchemy engine and session factories."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_domain.config import DomainSettings


def create_domain_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    settings = DomainSettings.from_env()
    url = database_url or settings.database_url
    return create_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory.begin() as session:
        yield session
