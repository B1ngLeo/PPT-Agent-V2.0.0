"""Shared persistent domain primitives for the Instant PPT services."""

from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.ids import new_ulid

__all__ = ["create_domain_engine", "create_session_factory", "new_ulid"]
