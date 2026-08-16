# G02 persistent orchestrator evidence

## Result

G02 is complete. The deterministic PostgreSQL/Celery/Redis orchestration spike meets
all PLAN 5.5–5.7 checkpoints and preserves the frozen G00 contract boundary. The
machine-readable recovery matrix contains 73 passed tests, zero failed, and zero
skipped. Its SHA-256 is
`2AA9EB7F04732EF949F37A642C509179ABE2894BCAB4D8A02DA5AD7C5734DEE8`.

## Checkpoint mapping

| Checkpoint               | Engineering evidence                                                                                                                                                       | Result       |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| CP-02A state truth       | Alembic upgrade → downgrade → upgrade; autogenerate drift check; PostgreSQL snapshot after Redis DB flush; transaction-validated job/slide lifecycles                      | passed       |
| CP-02B idempotency/races | 8-thread same-key create, changed-body conflict, unique event/manifest/reservation assertions, duplicate worker delivery, cancel/publish row-lock race, partial completion | passed       |
| CP-02C SSE/recovery      | snapshot + DB replay + Redis handoff, Last-Event-ID replay, reset semantics, heartbeat, terminal close, Redis flush, outbox fanout                                         | passed       |
| Process recovery         | actual Celery Worker exits with injected code 86; PostgreSQL lease reconciliation requeues by lease-token dedupe key; second Worker resumes persisted slide                | 10/10 passed |

## Executed verification

- `python -m uv sync --frozen`: workspace and exact lock restored;
- `docker compose config --quiet`: local topology valid;
- Alembic `upgrade`, `downgrade base`, second `upgrade`, `current`, and `check`: passed;
- `pnpm verify:api`: Ruff plus 9 domain/API tests passed;
- `pnpm verify:worker`: vendor/boundary guards, Ruff, and 7 Worker tests passed;
- `pnpm verify:integration`: 73 integration cases passed in 83.52 seconds;
- required ten-round groups: Worker process kill, simulated crash, partial slide,
  cancel/publish race, Redis restart, outbox fanout, and SSE resume;
- additional cases: concurrent API idempotency, HTTP snapshot, invalid SSE cursor reset.

The generated [recovery results](recovery/g02-recovery-results.json) record every case,
duration, database/Redis versions, timestamps, JUnit digest, and command.

## Faults found and closed

| Finding                                                                                                             | Attempts | Resolution                                                                                                                                                            |
| ------------------------------------------------------------------------------------------------------------------- | -------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ORM flush ordered a job before its composite-FK snapshot                                                            |        1 | Explicitly flush the immutable snapshot before inserting its dependent job.                                                                                           |
| Redis subscriber test published before consuming the subscribe acknowledgement                                      |        1 | Complete the Pub/Sub handshake before dispatching the outbox event.                                                                                                   |
| Abrupt Windows solo Worker exit left a late-ack Redis message unacknowledged beyond the requested visibility window |        3 | Retained late ack and bounded prefetch, aligned Celery/transport visibility settings, and added PostgreSQL expired-lease reconciliation with lease-token task dedupe. |

No issue exceeded the five-attempt limit. There are no deferred G02 defects or SPEC
deviations.
