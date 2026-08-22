# G08 observability and release design

## Boundary

G08 hardens the existing P1 flow; it does not add P1.1 features or perform a
production deployment. PostgreSQL remains the authority for business state, Redis is
only a delivery accelerator, and every object key remains tenant-prefixed and private.

## Telemetry

The API exposes `/internal/metrics` for an internal Prometheus scrape. HTTP counters,
latency histograms, active requests, authorization denials, SSE connections/reconnects/
replays/resets, and durable database aggregates use bounded labels. Resource IDs,
subjects, filenames, prompts, document bodies, tokens, signed URLs, and secrets are
never metric labels.

The database collector exposes source scan/parse state and duration, generation queue/
first-preview/terminal duration, per-stage slide state, export and artifact state,
outbox age, usage reservation/settlement, Provider call/token/duration aggregates,
cleanup state, audit actions, and reconciliation state. Current-state gauges are
explicitly distinct from process-local counters.

ISSUE-003 adds durable low-cardinality aggregates for explicit authoring mode/status,
fallback and `needs_manual` decisions, Strategist/Executor turns, input/output tokens,
configured micro-unit cost, bounded phase duration, allowlisted tool outcomes, page writes,
and repair attempts. Per-page/per-deck evidence remains in hash-bound workflow/manifest
artifacts; tenant IDs, PNNs, filenames, prompts, and source text are never metric labels.

FastAPI and Celery create OpenTelemetry spans with W3C trace IDs. OTLP HTTP export is
enabled only when an endpoint is configured; local development explicitly uses
`OTEL_TRACES_EXPORTER=none`. Span attributes are allowlisted correlation identifiers.
ASGI request bodies and headers are not captured. The worker task base records the task
name, task ID, bounded resource/organization IDs, error type, and trace ID without
content.

Structured request logs include request ID, trace ID, normalized route, status, method,
duration and authenticated organization ID. Dynamic paths and user input are not used
as metric labels.

## Alert and operational model

[Prometheus rules](../../infra/observability/alerts.yml) cover API error/latency,
SSE resets, outbox delay, generation/source timeout, Provider failure ratio,
reconciliation alerts, authorization spikes, and missing/stale scanner signatures.
Agent canary failure ratio and deterministic-template fallback ratio are separate alerts;
fallback never contributes to Agent success. Security, tenant isolation, grounding,
cancellation/recovery, compatibility, or publication-consistency failures trigger the
feature-flag rollback runbook. Visual preference regression alone requires human review.
Every alert links to [the runbook](../runbook.md). Scanner signature age is supplied by
the ClamAV exporter in a deployment environment; `absent()` fails closed if that
external security signal disappears.

## Recovery and release evidence

Object reconciliation lists only the current tenant prefix, protects active upload
sessions, removes expired/orphan objects, fails closed when a published database row
has no object, and records every run durably. Backup restore uses an isolated database
and restore bucket, compares the Alembic head and core table counts, and compares every
object SHA-256 before deleting the temporary targets.

The private bucket is provisioned fail-closed, removes any pre-existing public policy,
enables default SSE-S3 and applies a safe lifecycle rule for expired delete markers under
`tenants/`. PostgreSQL `retention_expires_at` plus
tenant-scoped reconciliation remains the authority for current-object expiry; bucket
lifecycle never guesses a user's retention window. MinIO separately expires stale
multipart uploads after 24 hours and scans for them hourly. The Compose static KMS key is
development-only verification material; a production deployment must use approved
KES/KMS configuration.

The fixed performance profile uses the release API image with four Uvicorn workers,
100 organizations, 1,000 drafts, 10,000 events, 1,000 artifacts, 20 virtual users,
120 seconds of warmup and 600 seconds of measurement. Results, exact image digests and
hardware are immutable evidence under `docs/evidence/performance/`.

Automated evidence may move the final Gate to `ready_for_review`; it cannot approve the
Windows screen-reader or production Provider/privacy decision.
