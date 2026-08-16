from __future__ import annotations

from typing import Any

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.service import (
    SYNTHETIC_ACTOR_ID,
    SYNTHETIC_ORGANIZATION_ID,
    CreateJobCommand,
    create_generation_job,
)
from sqlalchemy.orm import Session, sessionmaker


def create_job(
    session_factory: sessionmaker[Session],
    *,
    key: str | None = None,
    slide_count: int = 3,
    failure_modes: dict[int, str] | None = None,
    crash_once_at_position: int | None = None,
    step_delay_ms: int = 0,
    body_override: dict[str, Any] | None = None,
) -> str:
    body = body_override or {
        "schemaVersion": 1,
        "data": {
            "slideCount": slide_count,
            "failureModes": failure_modes or {},
            "crashOnceAtPosition": crash_once_at_position,
            "stepDelayMs": step_delay_ms,
        },
        "baseRevisionId": None,
    }
    with session_factory.begin() as session:
        result = create_generation_job(
            session,
            CreateJobCommand(
                organization_id=SYNTHETIC_ORGANIZATION_ID,
                actor_id=SYNTHETIC_ACTOR_ID,
                draft_id="01ARZ3NDEKTSV4RRFFQ69G5FAC",
                idempotency_key=key or f"g02-{new_ulid()}",
                request_body=body,
                intent_revision_id="01ARZ3NDEKTSV4RRFFQ69G5FAD",
                outline_revision_id="01ARZ3NDEKTSV4RRFFQ69G5FAE",
                template_version_id="01ARZ3NDEKTSV4RRFFQ69G5FAF",
                slide_count=slide_count,
                failure_modes=failure_modes or {},
                crash_once_at_position=crash_once_at_position,
                step_delay_ms=step_delay_ms,
            ),
        )
    return result.job_id
