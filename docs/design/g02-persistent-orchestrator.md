# G02 persistent orchestrator design

## Purpose and boundary

G02 proves the durable orchestration contract without a real source parser, AI
provider, PPT engine, login flow, or product UI. PostgreSQL owns business state;
Redis is only a Celery broker and low-latency event fanout. The deterministic Fake
Worker publishes small fixture manifests so recovery behavior is observable without
introducing rendering variability.

The implementation is split into:

- `packages/domain`: models, migrations, lifecycle validation, transactions,
  outbox dispatch, lease reconciliation, and the Fake Worker;
- `services/api`: job creation/snapshot/cancel/retry routes and SSE delivery;
- `services/worker`: Celery task boundary and the standalone outbox/recovery runner;
- `tests/integration/g02`: PostgreSQL, Redis, API, SSE, process-kill, and race tests;
- `scripts/g02/verify_integration.py`: isolated database setup and evidence capture.

## Persistence model

The first Alembic revision creates tenant-scoped rows for organizations, synthetic
service actors, immutable generation snapshots, jobs, job slides, events, outbox
records, idempotency records, published fixture manifests, and usage reservations.
Composite foreign keys bind snapshots, jobs, slides, actors, and side effects to one
organization from the first migration. G03 can add users and memberships without
rewriting G02 data.

Identifiers are monotonic ULIDs. Timestamps are timezone-aware UTC. PostgreSQL
checks constrain job/slide lifecycle values and counters; service methods additionally
validate every transition while holding the relevant row lock.

## Transaction and idempotency boundaries

Job creation takes a transaction-scoped PostgreSQL advisory lock over
`organization + actor + route + Idempotency-Key`. It then:

1. validates or replays the idempotency record;
2. persists the immutable snapshot;
3. creates the job, slides, usage reservation, initial event, event outbox, and task
   outbox;
4. stores the exact first HTTP response and request hash.

The whole operation commits atomically. Reusing the key with the same canonical body
returns the original response; changing the body raises the stable conflict. Logical
slide task keys contain organization, snapshot, stage, and stable slide ID, never the
execution attempt. Unique manifest and reservation constraints prevent duplicate
publication or settlement.

Every business event increments `generation_jobs.latest_seq` under a job row lock and
is inserted with the corresponding event outbox in the same transaction. The
`(job_id, seq)` uniqueness constraint turns accidental sequence reuse into a hard
failure rather than silent event loss.

## Worker recovery

Celery uses late acknowledgement, reject-on-worker-loss, bounded prefetch, and a
bounded Redis visibility timeout. The Fake Worker commits at safe slide boundaries:
claim, slide start, slide result, and final publication are separate transactions.
Restarting a killed worker therefore resumes a persisted `running` slide instead of
repeating completed slides.

Broker restoration timing is not treated as a correctness dependency. The outbox
runner also scans expired PostgreSQL leases and emits a recovery task whose dedupe key
contains the persisted lease token. A broker-restored original task and a reconciled
task may both arrive; row locks, lease ownership, terminal no-op behavior, and unique
side-effect rows make duplicate delivery safe. This is also how Redis can be emptied
without losing the ability to reconstruct or resume a job.

Cancellation and publication lock the same job row. The first legal terminal
transaction wins. A terminal cancel request is an idempotent no-op; a worker observing
`cancel_requested` at a safe boundary finalizes `cancelled` without publishing a
presentation fixture.

## SSE delivery

The SSE endpoint first reads the PostgreSQL job snapshot, resolves `Last-Event-ID`
from either an event ULID or numeric sequence, and replays later database events in
sequence order. An unknown/pruned cursor emits explicit reset plus snapshot semantics.

After replay it subscribes to `job:{job_id}` for low-latency Redis notification, while
continuing to poll PostgreSQL by sequence. PostgreSQL polling closes the subscribe/replay
race and makes Redis loss harmless. Events at or below the delivered sequence are
discarded; heartbeat frames do not consume business sequence numbers. A terminal event
closes the stream, and a later reconnect can still read the terminal snapshot.

## Verification boundary

The stable runner creates a dedicated PostgreSQL database and isolated Redis DB 14/15,
applies Alembic, enables real Celery process termination, and writes JUnit-derived
evidence. Each required crash, race, Redis, outbox, and SSE recovery case runs ten
times. See [G02 engineering evidence](../evidence/g02-persistent-orchestrator.md) and
the [machine-readable recovery matrix](../evidence/recovery/g02-recovery-results.json).
