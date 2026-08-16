# P1 operations runbook

## Service map and safe startup

- `api`: tenant-authenticated HTTP/SSE, internal Prometheus endpoint, four Uvicorn workers.
- `outbox`: dispatches committed PostgreSQL outbox rows to Redis/Celery.
- `worker`: source, generation, regeneration, export, cleanup and reconciliation tasks.
- PostgreSQL: authoritative state/audit/events; Redis: non-authoritative delivery; MinIO:
  private tenant-prefixed objects; ClamAV: fail-closed scan boundary.

For a local recovery rehearsal, start dependencies, migrate, then start runtime services:

```powershell
docker compose up -d postgres redis minio clamav
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini upgrade head
docker compose --profile runtime up -d api worker outbox
```

Confirm health, `/internal/metrics`, outbox age, and the current Alembic revision before
admitting traffic. Never put the metrics endpoint on a public ingress.

## API errors or latency

1. Correlate the normalized route, request ID and W3C trace ID. Do not search logs by
   prompts or document content.
2. Compare active requests, p95 histogram, 5xx rate, database connections and container
   CPU/memory. Confirm all four API workers are alive.
3. If PostgreSQL is healthy but saturated, reduce admission rate; do not increase pool
   sizes beyond the database connection budget.
4. For a release regression, roll back the application image using
   [the rollback procedure](rollback.md); keep the database at the newer compatible head.

## Queue or worker stall

1. Inspect `instant_ppt_oldest_outbox_pending_seconds`, running job age, Celery queue,
   worker heartbeat/lease and the durable job event sequence.
2. Restart a failed outbox or worker process. Do not edit job state or delete outbox rows.
3. Expired leases are reclaimed by the durable worker path; duplicate task delivery is
   expected and idempotent.
4. If a job crosses the 30-minute hard timeout, allow the configured recovery/cancel path
   to decide the terminal state. Never manufacture a publication row.

## SSE replay or Redis degradation

PostgreSQL events are authoritative. Restart Redis if needed, then reconnect with the
client's last event sequence. A `reset` response means the cursor is unavailable and the
client must fetch the job snapshot. Investigate a sustained reset rate; do not restore
Redis data by rewriting PostgreSQL event sequences.

## Source scan or parse failure

Scanner unavailability, stale signatures, MIME mismatch, encryption, active HTML and
archive expansion risk fail closed. Check ClamAV health and `clamav_signature_age_seconds`.
Only retry after the scanner/exporter is healthy. Never bypass quarantine or mark a
source clean manually. Parsing remains after clean promotion.

## Provider degradation

P1 can keep deterministic Fake Provider regression available, but a production traffic
switch requires an approved model, region, retention policy and supplier terms. Disable
the external Provider adapter when error/limit ratios rise; do not log or copy prompts to
incident tickets. Existing durable revisions and exports remain available.

## Authorization denial spike

Group only by external status and route. Sample request/trace IDs, verify issuer/audience,
membership state and tenant predicates, and look for enumeration patterns. Cross-tenant
lookups must continue returning uniform 404 responses. Treat any confirmed disclosure as
Sev-1 and stop release.

## Object-store divergence

Run reconciliation first in dry-run mode for the affected organization. The worker task
is `instant_ppt.reconcile_objects`; it must receive the exact organization ID and tenant
prefix. Active upload sessions are protected. Missing published objects are revoked and
alerted; expired/orphan objects are removed. Review the durable
`object_reconciliation_runs` record before clearing the alert. Never run an unscoped
bucket delete.

## Backup and restore

The reproducible local rehearsal is:

```powershell
python -m uv run --package instant-ppt-worker python scripts/g08/run_backup_restore.py
```

Production restore must use newly created, explicitly named database and bucket targets.
Validate the Alembic revision, core counts and object hashes before changing any routing.
Keep the source backup immutable until post-restore application smoke checks pass. The
rehearsal cleans only `instant_ppt_g08_restore`, its exact backup file, and
`instant-ppt-g08-restore`.

## Retention and deletion

Idempotency/events default to seven days, temporary artifacts to 24 hours, and download
grants to 15 minutes. Project deletion first revokes access and cancels work, then runs
auditable cleanup. Verify API/SSE/download 404 behavior and object removal. Never shorten
retention or delete Provider caches without the approved policy and tenant scope.

