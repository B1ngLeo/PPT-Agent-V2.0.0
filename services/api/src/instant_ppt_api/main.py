"""FastAPI application factory."""

from fastapi import FastAPI
from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_api.routes import router


def create_app(
    *,
    settings: DomainSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Create the API with injectable persistence for integration tests."""
    resolved_settings = settings or DomainSettings.from_env()
    resolved_factory = session_factory or create_session_factory(
        create_domain_engine(resolved_settings.database_url)
    )
    application = FastAPI(title="即刻AI-PPT API", version="0.0.0")
    application.state.settings = resolved_settings
    application.state.session_factory = resolved_factory
    application.include_router(router)
    return application


app = create_app()
