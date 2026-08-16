from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from instant_ppt_domain.fake_worker import InjectedWorkerCrash, process_fake_job
from instant_ppt_domain.models import GenerationJob, IdempotencyRecord, JobEvent
from instant_ppt_domain.outbox import dispatch_outbox_batch
from instant_ppt_domain.service import (
    SYNTHETIC_ACTOR_ID,
    SYNTHETIC_ORGANIZATION_ID,
    CreateJobCommand,
    IdempotencyConflict,
    claim_job,
    complete_slide,
    count_job_side_effects,
    create_generation_job,
    finalize_job,
    get_job,
    list_events_after,
    request_cancel,
    start_next_slide,
)
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .helpers import create_job


def _read_job(session_factory: sessionmaker[Session], job_id: str) -> GenerationJob:
    with session_factory() as session:
        job = get_job(session, job_id, SYNTHETIC_ORGANIZATION_ID)
        session.expunge(job)
        return job


def test_idempotency(session_factory: sessionmaker[Session]) -> None:
    body = {"schemaVersion": 1, "data": {"slideCount": 3}, "baseRevisionId": None}

    def submit(request_body: dict = body) -> str:
        with session_factory.begin() as session:
            result = create_generation_job(
                session,
                CreateJobCommand(
                    organization_id=SYNTHETIC_ORGANIZATION_ID,
                    actor_id=SYNTHETIC_ACTOR_ID,
                    draft_id="01ARZ3NDEKTSV4RRFFQ69G5FAC",
                    idempotency_key="concurrent-same-key",
                    request_body=request_body,
                    intent_revision_id="01ARZ3NDEKTSV4RRFFQ69G5FAD",
                    outline_revision_id="01ARZ3NDEKTSV4RRFFQ69G5FAE",
                    template_version_id="01ARZ3NDEKTSV4RRFFQ69G5FAF",
                    slide_count=3,
                ),
            )
            return result.job_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        job_ids = list(executor.map(lambda _: submit(), range(8)))
    assert len(set(job_ids)) == 1
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(GenerationJob)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert count_job_side_effects(session, job_ids[0])["reservations"] == 1
    with pytest.raises(IdempotencyConflict):
        submit({"schemaVersion": 1, "data": {"slideCount": 4}, "baseRevisionId": None})


@pytest.mark.parametrize("iteration", range(10))
def test_worker_crash_recovery(
    session_factory: sessionmaker[Session], iteration: int
) -> None:
    job_id = create_job(
        session_factory,
        key=f"crash-{iteration}",
        slide_count=3,
        crash_once_at_position=2,
    )
    with pytest.raises(InjectedWorkerCrash):
        process_fake_job(session_factory, job_id, "stable-task-id")
    assert _read_job(session_factory, job_id).status == "running"
    assert process_fake_job(session_factory, job_id, "stable-task-id") == "succeeded"
    assert process_fake_job(session_factory, job_id, "duplicate-delivery") == "noop_terminal"
    with session_factory() as session:
        effects = count_job_side_effects(session, job_id)
        events = list_events_after(session, job_id, SYNTHETIC_ORGANIZATION_ID, 0)
        assert effects["manifests"] == 1
        assert effects["reservations"] == 1
        assert [event.seq for event in events] == list(range(1, len(events) + 1))
        assert len({event.id for event in events}) == len(events)


@pytest.mark.parametrize("iteration", range(10))
def test_partial_slide_completion(
    session_factory: sessionmaker[Session], iteration: int
) -> None:
    job_id = create_job(
        session_factory,
        key=f"partial-{iteration}",
        slide_count=3,
        failure_modes={2: "always"},
    )
    assert process_fake_job(session_factory, job_id, f"partial-worker-{iteration}") == (
        "partially_succeeded"
    )
    job = _read_job(session_factory, job_id)
    assert job.progress_completed == 2
    with session_factory() as session:
        events = list_events_after(session, job_id, SYNTHETIC_ORGANIZATION_ID, 0)
        assert sum(event.event_type == "slide.failed" for event in events) == 1
        assert events[-1].event_type == "job.partially_completed"
        assert count_job_side_effects(session, job_id)["manifests"] == 1


@pytest.mark.parametrize("iteration", range(10))
def test_cancel_publish_race(
    session_factory: sessionmaker[Session], iteration: int
) -> None:
    job_id = create_job(session_factory, key=f"race-{iteration}", slide_count=1)
    worker_id = f"race-worker-{iteration}"
    with session_factory.begin() as session:
        claim_job(session, job_id, worker_id, lease_seconds=30)
    with session_factory.begin() as session:
        slide = start_next_slide(session, job_id, worker_id)
    assert slide is not None
    with session_factory.begin() as session:
        complete_slide(session, job_id, slide.slide_id, worker_id, succeeded=True)

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def publish() -> None:
        try:
            barrier.wait()
            with session_factory.begin() as session:
                finalize_job(session, job_id, worker_id)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    def cancel() -> None:
        try:
            barrier.wait()
            with session_factory.begin() as session:
                request_cancel(session, job_id, SYNTHETIC_ORGANIZATION_ID)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    threads = [threading.Thread(target=publish), threading.Thread(target=cancel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors
    job = _read_job(session_factory, job_id)
    if job.status == "cancel_requested":
        with session_factory.begin() as session:
            finalize_job(session, job_id, worker_id)
        job = _read_job(session_factory, job_id)
    assert job.status in {"succeeded", "cancelled"}
    with session_factory() as session:
        terminal_events = session.scalars(
            select(JobEvent).where(
                JobEvent.job_id == job_id,
                JobEvent.event_type.in_(("job.completed", "job.cancelled")),
            )
        ).all()
        assert len(terminal_events) == 1
        assert count_job_side_effects(session, job_id)["manifests"] in {0, 1}


@pytest.mark.parametrize("iteration", range(10))
def test_redis_restart(
    session_factory: sessionmaker[Session], redis_events_url: str, iteration: int
) -> None:
    job_id = create_job(session_factory, key=f"redis-{iteration}", slide_count=2)
    assert process_fake_job(session_factory, job_id, f"redis-worker-{iteration}") == "succeeded"
    Redis.from_url(redis_events_url).flushdb()
    with session_factory() as session:
        job = get_job(session, job_id, SYNTHETIC_ORGANIZATION_ID)
        events = list_events_after(session, job_id, SYNTHETIC_ORGANIZATION_ID, 0)
        assert job.status == "succeeded"
        assert job.latest_seq == len(events)
        assert events[-1].event_type == "job.completed"


@pytest.mark.parametrize("iteration", range(10))
def test_outbox_redis_fanout(
    session_factory: sessionmaker[Session], redis_events_url: str, iteration: int
) -> None:
    job_id = create_job(session_factory, key=f"outbox-{iteration}", slide_count=1)
    redis_client = Redis.from_url(redis_events_url, decode_responses=True)
    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(f"job:{job_id}")
    # Consume the SUBSCRIBE acknowledgement before publishing. With ignored
    # subscribe messages this returns None while still completing the handshake.
    pubsub.get_message(timeout=1)
    published_tasks: list[tuple[str, dict, str]] = []
    dispatched = dispatch_outbox_batch(
        session_factory,
        redis_client,
        lambda destination, payload, key: published_tasks.append((destination, payload, key)),
    )
    message = pubsub.get_message(timeout=1)
    pubsub.close()
    redis_client.close()
    assert dispatched == 2
    assert message is not None
    assert published_tasks[0][0] == "instant_ppt.process_fake_job"
    assert published_tasks[0][1] == {"jobId": job_id}
