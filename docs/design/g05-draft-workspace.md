# G05 draft, intent, outline, and Web workspace design

## Purpose and stop boundary

G05 turns a topic or a G04 parsed source into a recoverable planning workspace. It
owns built-in template selection, Draft persistence, editable Intent and Outline
revisions, AI-assisted revisions, undo/redo, optimistic conflict handling, history,
and an explicit approval snapshot. It intentionally stops before generation: an
approval does not create a generation job, call the PPT engine, or call the image
provider.

## Domain and persistence

Three built-in native templates are seeded idempotently. A Draft points to one exact
immutable template version and advances pointers to the latest Intent and Outline
revision. Revisions are append-only; PostgreSQL triggers reject update and delete on
template versions, Intent revisions, Outline revisions, Outline slides, and approval
snapshots. Undo and redo therefore copy a historical value into a new revision rather
than moving or rewriting history.

Every Outline slide has a stable `outlineSlideId`. Reordering changes position only;
editing preserves the ID; adding creates a new ID. An approval stores the exact Intent,
Outline, template version, mode, source summary, and a deterministic input hash. Later
edits advance the Draft pointer but cannot mutate that approval.

Provider calls store provider/model, request and response hashes, token counts, status,
latency, request ID, and a sanitized error. Prompt text, source text, authorization
headers, and reasoning traces are not persisted.

## API and conflict model

The tenant-scoped FastAPI surface includes:

- Draft create/read/update/soft-delete and persisted history;
- Intent infer/create/get/list;
- Outline generate/create/get/list and explicit revision approval;
- built-in template catalog and exact version lookup.

Mutation envelopes use schema version 1 and a client-generated ASCII idempotency key.
Draft field updates use `If-Match`/ETag and return `412` for stale writers. Revision
creation carries `baseRevisionId` and also returns `412` when another writer has
advanced the pointer. Cross-tenant and unknown identifiers both return `404`.

The Web app saves editable fields after an 800 ms debounce. A failed request leaves the
current React value intact, enters a stable failure state, and waits for an explicit
retry; it does not retry-loop. Refresh reconstructs the workspace from the Draft
snapshot and revision lists. The URL contains only the Draft ID.

## Provider boundary

Planning defaults to `DeterministicFakeProvider` for repeatable contracts and offline
development. The Worker-only provider adapter reads `MOONSHOT_API_KEY` and targets the
frozen PLAN setting `kimi-k3`; its structured gateway accepts JSON object output and
performs at most two schema-repair attempts. The neutral completion object excludes
reasoning content. Sanitized exceptions expose only provider, status, and safe request
ID.

The image adapter is preconfigured for the frozen `gpt-image-2` setting, but G05 never
invokes it. As checked on 2026-08-16, the current official public model lists used in
implementation research did not establish either frozen model name. The repository
therefore preserves the specified names without claiming production availability. A
real text smoke is conditional on both a locally supplied secret and provider support;
the deterministic provider remains the P1 regression baseline.

## Web interaction and responsive behavior

The homepage obtains templates, entitlement limits, usage, and history from the API.
It accepts either a topic or one parsed source, exposes only native mode, and labels the
primary action `生成大纲`. The workspace includes a fully editable Intent form, story
summary, per-slide editing, add/delete/move, undo/redo, AI rewrite/optimization, save
state, revision IDs, approval summary, and a disabled G06 action.

- At 1200 px and above the editor and assistant use an approximately 70/30 layout.
- From 768 to 1199 px templates and slides use two columns and the assistant is an
  operable native `details` drawer.
- Below 768 px the interface is single-column and the four-step indicator scrolls
  horizontally.

Controls use semantic buttons, labels, live save/error status, a native dialog with
focus restoration, visible focus treatment, reduced-motion handling, and minimum
44×44 px touch targets. No tested viewport introduces page-level horizontal overflow.

## Verification boundary

Provider request/error/repair tests, real PostgreSQL integration tests, immutable
database trigger tests, tenant/conflict/idempotency cases, production Web build, and
an in-app Chromium user journey form the G05 gate. Machine-readable browser and
provider-security evidence lives under `docs/evidence`. The browser harness could focus
and type but did not inject Tab/Enter activation after five attempts; the issue is
recorded per the project loop rule, with native semantic controls, focus restoration,
keyboard text entry, and the completed real user journey as compensating checks.
