# 即刻AI-PPT system design baseline

## Boundaries

The monorepo has four deployable or reusable boundaries:

1. `apps/web`: Next.js product UI and browser-facing BFF only.
2. `services/api`: FastAPI authorization, domain APIs and SSE; no heavy parsing or PPT generation.
3. `services/worker`: Celery orchestration, isolated parsing/generation and Provider Gateway.
4. `packages/contracts`: versioned OpenAPI, JSON Schema, fixtures, state machines and generated client types.

PostgreSQL is the business truth source. Redis carries queues, short-lived cache and event fan-out; losing Redis cannot alter final state. Private S3-compatible storage holds source and generated artifacts across `quarantine`, `clean`, `tmp` and `published` partitions. The scanner and parser fail closed.

## Versioned artifact flow

`SourcePackage → IntentSpec → OutlineSpec → GenerationSnapshot(authoringPolicy) → PageBlueprint → Main Agent turn/tool evidence | deterministic-template fallback → canonical SVG/content/visual QA → generation manifest → PresentationRevision → ExportManifest`

Approved intent, outline, template version, generation snapshot, presentation revision and published artifacts are immutable. User edits create new revisions. Download URLs are short-lived authorization results, not stored artifact identity.

## Runtime invariants

- Web/API never invoke upstream engine internals.
- The engine adapter never receives business database credentials or browser sessions.
- State changes, job events and outbox records commit atomically.
- Object publication occurs only after contract and QA checks.
- Stable slide identifiers survive reordering and retries.
- Every organization-scoped query, event stream and object authorization repeats tenant checks.
- `default-agentic` means a real, resumable Strategist/Executor model-tool loop. Each page author receipt binds the current SVG hash to persisted turn/tool evidence; reviewer observations are read-only inputs and repairs remain owned by the Main Agent.
- `deterministic-template` is an explicit rollback profile with no text-Provider or Agent-tool calls. Its state, manifest, metrics, UI, and filename disclose a template-limited draft and cannot be counted as Agent authorship.
- The server freezes authoring mode and visual-review policy in the snapshot. Changing the feature flag affects only newly created snapshots; exact exports keep the immutable revision bytes.
