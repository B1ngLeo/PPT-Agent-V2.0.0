"""Database replay plus Redis-assisted live SSE handoff."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Request
from instant_ppt_domain.models import JobEvent
from instant_ppt_domain.service import (
    ResourceNotFound,
    get_job,
    list_events_after,
    serialize_event,
)
from instant_ppt_domain.state import is_terminal_job
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker


def _sse(event: str, data: dict, event_id: str | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    lines.append(f"data: {encoded}")
    return "\n".join(lines) + "\n\n"


def _load_state(
    session_factory: sessionmaker[Session],
    job_id: str,
    organization_id: str,
    after_seq: int,
) -> tuple[dict, list[dict]]:
    with session_factory() as session:
        job = get_job(session, job_id, organization_id)
        snapshot = {
            "schemaVersion": 1,
            "jobId": job.id,
            "status": job.status,
            "stage": job.stage,
            "latestSeq": job.latest_seq,
            "terminal": is_terminal_job(job.status),
        }
        events = [
            serialize_event(event)
            for event in list_events_after(session, job_id, organization_id, after_seq)
        ]
        return snapshot, events


def _resolve_last_seq(
    session_factory: sessionmaker[Session],
    job_id: str,
    organization_id: str,
    last_event_id: str | None,
) -> int | None:
    if last_event_id is None or last_event_id == "":
        return 0
    if last_event_id.isdigit():
        return int(last_event_id)
    with session_factory() as session:
        get_job(session, job_id, organization_id)
        event = session.scalar(
            select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id == last_event_id)
        )
        return event.seq if event is not None else None


async def stream_events(
    request: Request,
    session_factory: sessionmaker[Session],
    *,
    redis_url: str,
    job_id: str,
    organization_id: str,
    last_event_id: str | None,
    heartbeat_seconds: float,
) -> AsyncIterator[str]:
    last_seq = await asyncio.to_thread(
        _resolve_last_seq,
        session_factory,
        job_id,
        organization_id,
        last_event_id,
    )
    snapshot, _ = await asyncio.to_thread(_load_state, session_factory, job_id, organization_id, 0)
    if last_seq is None or last_seq > snapshot["latestSeq"]:
        yield _sse(
            "reset",
            {
                "schemaVersion": 1,
                "jobId": job_id,
                "reason": "sequence_unavailable",
                "snapshotUrl": f"/v1/jobs/{job_id}",
                "latestSeq": snapshot["latestSeq"],
            },
        )
        return

    redis_client: Redis | None = None
    pubsub = None
    try:
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(f"job:{job_id}")
    except RedisError:
        if pubsub is not None:
            await pubsub.aclose()
        if redis_client is not None:
            await redis_client.aclose()
        pubsub = None
        redis_client = None

    delivered_seq = last_seq
    try:
        if last_event_id is None:
            yield _sse("snapshot", snapshot, str(snapshot["latestSeq"]))
        while not await request.is_disconnected():
            current, events = await asyncio.to_thread(
                _load_state,
                session_factory,
                job_id,
                organization_id,
                delivered_seq,
            )
            for event in events:
                seq = int(event["seq"])
                if seq <= delivered_seq:
                    continue
                delivered_seq = seq
                yield _sse(str(event["type"]), event, str(seq))
            if current["terminal"] and delivered_seq >= current["latestSeq"]:
                return
            if pubsub is None:
                await asyncio.sleep(min(heartbeat_seconds, 1.0))
            else:
                try:
                    message = await pubsub.get_message(timeout=heartbeat_seconds)
                except RedisError:
                    message = None
                    await pubsub.aclose()
                    await redis_client.aclose()
                    pubsub = None
                    redis_client = None
                if message is None:
                    yield ": heartbeat\n\n"
    except ResourceNotFound:
        return
    finally:
        if pubsub is not None:
            await pubsub.unsubscribe(f"job:{job_id}")
            await pubsub.aclose()
        if redis_client is not None:
            await redis_client.aclose()
