# 即刻AI-PPT system design baseline

## Boundaries

The monorepo has four deployable or reusable boundaries:

1. `apps/web`: Next.js product UI and browser-facing BFF only.
2. `services/api`: FastAPI authorization, domain APIs and SSE; no heavy parsing or PPT generation.
3. `services/worker`: Celery orchestration, isolated parsing/generation and Provider Gateway.
4. `packages/contracts`: versioned OpenAPI, JSON Schema, fixtures, state machines and generated client types.

PostgreSQL is the business truth source. Redis carries queues, short-lived cache and event fan-out; losing Redis cannot alter final state. Private S3-compatible storage holds source and generated artifacts across `quarantine`, `clean`, `tmp` and `published` partitions. The scanner and parser fail closed.

## Versioned artifact flow

`SourcePackage → IntentSpec → OutlineSpec → GenerationSnapshot → DeckPlan/SlidePlan → canonical SVG/QA → generation manifest → PresentationRevision → ExportManifest`

Approved intent, outline, template version, generation snapshot, presentation revision and published artifacts are immutable. User edits create new revisions. Download URLs are short-lived authorization results, not stored artifact identity.

## Runtime invariants

- Web/API never invoke upstream engine internals.
- The engine adapter never receives business database credentials or browser sessions.
- State changes, job events and outbox records commit atomically.
- Object publication occurs only after contract and QA checks.
- Stable slide identifiers survive reordering and retries.
- Every organization-scoped query, event stream and object authorization repeats tenant checks.
