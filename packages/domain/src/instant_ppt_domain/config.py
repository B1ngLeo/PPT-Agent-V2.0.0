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
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: int = 10
    app_environment: str = "local"
    auth_mode: str = "local"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_algorithms: tuple[str, ...] = ("RS256",)
    oidc_clock_skew_seconds: int = 30
    download_url_ttl_seconds: int = 900
    upload_session_ttl_seconds: int = 600
    web_origin: str = "http://localhost:3000"

    def __post_init__(self) -> None:
        if self.app_environment not in {"local", "test", "staging", "production"}:
            raise ValueError("APP_ENVIRONMENT must be local, test, staging, or production")
        if self.auth_mode not in {"local", "oidc"}:
            raise ValueError("AUTH_MODE must be local or oidc")
        if self.app_environment in {"staging", "production"} and self.auth_mode == "local":
            raise ValueError("local authentication is forbidden outside local/test")
        if self.auth_mode == "oidc" and not (
            self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url
        ):
            raise ValueError("OIDC issuer, audience, and JWKS URL are required")
        if not self.oidc_algorithms or any(
            algorithm not in {"RS256", "RS384", "RS512"} for algorithm in self.oidc_algorithms
        ):
            raise ValueError("only explicitly configured RSA OIDC algorithms are supported")
        if not 15 <= self.download_url_ttl_seconds <= 900:
            raise ValueError("DOWNLOAD_URL_TTL_SECONDS must be between 15 and 900")
        if not 60 <= self.upload_session_ttl_seconds <= 900:
            raise ValueError("UPLOAD_SESSION_TTL_SECONDS must be between 60 and 900")
        if not 1 <= self.database_pool_size <= 100:
            raise ValueError("DATABASE_POOL_SIZE must be between 1 and 100")
        if not 0 <= self.database_max_overflow <= 100:
            raise ValueError("DATABASE_MAX_OVERFLOW must be between 0 and 100")
        if not 1 <= self.database_pool_timeout_seconds <= 60:
            raise ValueError("DATABASE_POOL_TIMEOUT_SECONDS must be between 1 and 60")

    @classmethod
    def from_env(cls) -> DomainSettings:
        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            redis_events_url=os.getenv("REDIS_EVENTS_URL", DEFAULT_REDIS_EVENTS_URL),
            celery_broker_url=os.getenv("CELERY_BROKER_URL", DEFAULT_CELERY_BROKER_URL),
            sse_heartbeat_seconds=float(os.getenv("SSE_HEARTBEAT_SECONDS", "20")),
            outbox_poll_seconds=float(os.getenv("OUTBOX_POLL_SECONDS", "0.25")),
            worker_lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "30")),
            database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
            database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "5")),
            database_pool_timeout_seconds=int(
                os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "10")
            ),
            app_environment=os.getenv("APP_ENVIRONMENT", "local").strip().lower(),
            auth_mode=os.getenv("AUTH_MODE", "local").strip().lower(),
            oidc_issuer=os.getenv("OIDC_ISSUER", "").strip(),
            oidc_audience=os.getenv("OIDC_AUDIENCE", "").strip(),
            oidc_jwks_url=os.getenv("OIDC_JWKS_URL", "").strip(),
            oidc_algorithms=tuple(
                value.strip()
                for value in os.getenv("OIDC_ALGORITHMS", "RS256").split(",")
                if value.strip()
            ),
            oidc_clock_skew_seconds=int(os.getenv("OIDC_CLOCK_SKEW_SECONDS", "30")),
            download_url_ttl_seconds=int(os.getenv("DOWNLOAD_URL_TTL_SECONDS", "900")),
            upload_session_ttl_seconds=int(os.getenv("UPLOAD_SESSION_TTL_SECONDS", "600")),
            web_origin=os.getenv("WEB_ORIGIN", "http://localhost:3000").rstrip("/"),
        )
