# G07 editor, exact export, history, and project lifecycle design

## Purpose and boundary

G07 turns the immutable G06 baseline into a bounded editable draft. It supports
text replacement, ordering, deletion, stable-slide regeneration, exact-revision
PPTX export, history recovery, project data export, and audited project deletion.
It intentionally does not introduce a free-form canvas, collaborative merging,
public sharing, PDF/image export, or private-template analysis.

## Immutable revision model

`presentations` owns the current revision pointer and optimistic `lock_version`.
Every accepted operation creates a new `presentation_revisions` row, an immutable
canonical payload, a SHA-256 digest, a revision manifest artifact, and a complete
set of `slide_versions`. PostgreSQL rejects revision UPDATE/DELETE. An operation
set must name the exact base revision; stale writers receive `412` and never merge
implicitly. Stable `slideId` values survive text edits, moves, and regeneration.
Deletion cannot reduce a deck below one page.

The approved outline and G06 generation snapshot are never mutated. A partial
revision cannot be exported until the user either retries/deletes failed pages or
adds the explicit `accept_missing` operation, which remains visible in revision
history.

## Single-slide regeneration

Regeneration queues a tenant-scoped `slide_regeneration_job` against a stable
slide ID and exact base revision. The published ready version remains current
while the Worker authors a candidate, renders it, and applies SVG QA. Only a
successful candidate is uploaded and atomically published as a new revision;
`source_slide_version_id` records the lineage. Failure leaves the old revision
and artifact usable.

## Exact export and download

An `export_job` binds `presentation_revision_id` and normalized options at queue
time. The Worker reconstructs a DeckPlan from that immutable revision, invokes
the sole G01 engine adapter, runs package QA, and publishes independent
`export_pptx` and `export_manifest` artifacts. Later edits cannot change the
running export. Usage settlement is idempotent per export.

Download authorization reuses the G03 tenant membership, active artifact,
retention, object-size, 15–900 second signature, grant, and audit checks. The Web
fetches the private cross-origin object into a Blob before triggering a named
download, so navigation never leaks the editor route. Expiration, idempotent
replay limits, re-signing, tamper rejection, and cross-tenant hiding remain owned
by the shared G03 authorization path.

## History and deletion

History reads real Draft/job/Presentation state and returns routes for draft,
monitor, or result recovery. Refreshing a result route resolves the authoritative
current revision rather than browser memory.

Project data export creates an immutable JSON snapshot artifact. Project deletion
first soft-deletes the Draft and Presentation so API, SSE, history, and new
download grants fail closed immediately. A durable cleanup job then cancels
running generation/regeneration/export work, removes every known private object,
and marks all related artifacts revoked and deleted. Its audited result reports
artifact, removed-object, and failed-object counts; retries are idempotent.

## Verification boundary

The G07 integration matrix covers optimistic immutable edits, minimum-page and
partial guards, atomic regeneration, exact-revision concurrent export, real PPTX
package structure, tenant denial, history recovery, data export, and cleanup. The
production-browser journey additionally covers an eight-page user edit/reorder/
regenerate/export/reload path, 390px layout, keyboard skip navigation, actual
PPTX/JSON files, and post-delete route/object denial.
