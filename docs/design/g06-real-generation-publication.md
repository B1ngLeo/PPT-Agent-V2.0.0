# G06 real generation, monitoring, and immutable publication design

## Purpose and boundary

G06 connects an exact G05 approval to the durable G02 orchestration model and the
G01 engine adapter. It owns quota reservation, an immutable generation snapshot,
stable per-slide execution, QA, deck compilation, package QA, object upload,
transactional publication, progress events, cancellation, and failed-slide retry.
It intentionally stops at the generated baseline: result editing, export jobs,
downloads, visual mode, and private templates belong to later goals.

A Product/Security/Legal-approved 2026-08-16 extension, completed by the 2026-08-19
ISSUE-002 Release Gate, adds an explicit bounded cover/selective image-resource step
without changing slide identity or the editable native baseline invariants.

## Snapshot and state ownership

Starting a native generation job locks the Draft and reads the current approval,
Intent revision, Outline revision, template version, mode, source summary, and all
frozen prompt/engine/container/font/provider versions in one transaction. The
snapshot also freezes the non-secret planning backend and image enablement, gateway URL,
model, format, size, quality and per-deck cap so queue delay or Worker restart cannot pick
up different Provider behavior. The canonical approved payload is stored in
`generation_snapshots`; its SHA-256 is
computed before adding the self-describing `snapshotSha256` field. PostgreSQL
triggers reject update and delete so later Draft edits cannot change Worker input.

PostgreSQL is the source of truth for job, stage, slide, lease, attempt, event
sequence, reservation, billing, artifact, publication, Presentation, revision, and
slide-version state. Redis is only the Celery transport and low-latency SSE fan-out.
The SSE endpoint always replays ordered events from PostgreSQL before waiting for
Redis, so a cache/broker restart or browser reconnect cannot lose durable progress.

Each Outline slide is mapped once to a stable generation `slideId`. Candidate work
commits at a per-slide boundary: content generation, rendering, QA, status, attempt,
render hash, and sanitized QA are persisted before the next page. A replacement
Worker can reclaim an expired lease and continue a `running` page without changing
its identity. Celery uses late acknowledgement, rejection on Worker loss, a
prefetch multiplier of one, bounded retries, and a visibility timeout; the domain
state machine remains the idempotence authority.

## Worker and engine boundary

The Worker is the only component that authors and renders. It reconstructs a
`DeckPlan` exclusively from the immutable snapshot, renders and QA-checks each page,
then invokes the public G01 `engine-adapter` request for full-deck compilation and
package QA. The engine never receives a database connection or tenant credentials.

The API maps the user's `image_scope=none|cover_only|selective` choice to the upstream
source-id array, per-page notes and declared AI path chain. `none` is exclusive. Runtime
configuration alone cannot opt a job into images. Before design, the Worker verifies and
copies provided assets into the project, creates a fresh `analysis/image_analysis.csv`,
and binds its inventory hash. Acquisition or replacement invalidates the old analysis.

For an AI row, the Worker derives a minimal text-free visual prompt, rejects factual/data,
UI, logo and person-evidence roles, and calls `gpt-image-2` at most once per deck under the
current entitlement. A stable idempotency key bounds retry duplication where the gateway
honors it. `auto` follows only the frozen path chain; explicit paths cannot switch provider.
An approved Office-native substitute runs only for its declared trigger. Otherwise a
required unresolved row records sanitized attempts and returns `Needs-Manual` before export.
The image is an independent, referenced, non-full-slide PPTX picture; title, body, charts
and evidence remain native editable objects.

Successful or partial runs produce deterministic files:

- `generation_source_bundle` with canonical JSON and normalized workspace paths;
- `generation_baseline_pptx` from the native engine path;
- `generation_preview_svg` and `generation_qa_report`;
- optional image source asset(s), `generation_image_analysis`, `generation_image_audit`
  and prompt-hash manifest, included in the source bundle and PPTX media as applicable;
- one `generation_slide_svg` for each newly successful stable slide;
- one `generation_manifest` binding the snapshot, all frozen versions, publication,
  Presentation/revision identities, artifact metadata, ready/failed slide IDs, and
  reused artifacts.

Artifact IDs and private object keys derive deterministically from job, publication
version, kind, and optional slide ID. Upload happens before the database transaction;
a crash can therefore leave unreferenced objects, but retry writes identical bytes to
the same keys. No object is published to users until the single database transaction
creates artifact rows, the generation publication, Presentation/revision/slide
versions, usage settlement, audit, and terminal events. Immutable triggers protect
published identities and revision history.

## Partial, retry, cancellation, and accounting

A page failure does not stop later pages. The compiled baseline retains the failed
slot, publication status is partial, and an initial partial Presentation revision is
created if at least one page is ready. Manual retry is addressed by stable `slideId`,
reopens only that page, and creates a new publication/revision. Previously ready SVG
artifacts are reused when their final render hash is unchanged, and their slide usage
is not charged twice.

Cancellation is idempotent. A queued or running job moves to `cancel_requested`; the
Worker checks before compile and the publication transaction locks and checks again.
If cancellation races after upload but before publish, cancellation wins, no Artifact,
Publication, Presentation, or revision row is created, and reservations are settled
or released exactly once. Failed and cancelled jobs with no usable page create no
Presentation. Quota is checked against settled plus reserved slides under the tenant
lock before a job is created.

Planning input/output tokens are settled when their ProviderCall succeeds. Before job
creation, tenant-scoped locking checks and reserves image count plus configured micro-unit
cost together with slides. Generation settles actual published generated image count/cost
exactly once; provided/native/manual/failed paths settle no Provider image cost, and
cancel/failure releases unused reservation.

## Monitoring and accessibility

The Web monitor restores from `?draft=…&job=…`, fetches authoritative state, and then
opens a fetch-based SSE stream with `Last-Event-ID`. Reconnect uses bounded exponential
backoff and does not restart merely because a state refresh returned a new object.
The UI maps the real five-stage pipeline, connection state, durable event sequence,
stable slide cards, retry controls, cancellation, immutable publication identity, and
the five deck-level artifact kinds. Native buttons, live regions, a semantic progress
element, visible focus, reduced-motion behavior, 44 px controls, and responsive grid
breakpoints follow the established workspace design system.

The monitor deliberately exposes no baseline download or editing control in G06; it
labels those capabilities as G07 work.

## Verification boundary

The G06 integration matrix uses real PostgreSQL, MinIO, Redis, the public engine
adapter, and native PPTX package inspection. It covers abrupt OS process death,
upload-before-transaction replay, duplicate delivery, actual Redis container restart
plus SSE sequence replay, partial/retry reuse, both cancellation boundaries, quota,
tenant hiding, immutable triggers, artifact hashes, and exactly-once usage. A clean
production Web build and real browser journey cover approval through real Worker
publication and URL refresh recovery.
