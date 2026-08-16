# G06 real generation, monitoring, and immutable publication design

## Purpose and boundary

G06 connects an exact G05 approval to the durable G02 orchestration model and the
G01 engine adapter. It owns quota reservation, an immutable generation snapshot,
stable per-slide execution, QA, deck compilation, package QA, object upload,
transactional publication, progress events, cancellation, and failed-slide retry.
It intentionally stops at the generated baseline: result editing, export jobs,
downloads, visual mode, image generation, and private templates belong to later
goals.

## Snapshot and state ownership

Starting a native generation job locks the Draft and reads the current approval,
Intent revision, Outline revision, template version, mode, source summary, and all
frozen prompt/engine/container/font/provider versions in one transaction. The
canonical approved payload is stored in `generation_snapshots`; its SHA-256 is
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

Successful or partial runs produce deterministic files:

- `generation_source_bundle` with canonical JSON and normalized workspace paths;
- `generation_baseline_pptx` from the native engine path;
- `generation_preview_svg` and `generation_qa_report`;
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
