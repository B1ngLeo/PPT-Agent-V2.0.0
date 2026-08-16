# ADR-011: Separate source, generation, slide and export lifecycles

- Status: accepted
- Date: 2026-08-16
- Owners: engineering
- Related SPEC: 6.7, 6.8, 6.10

## Decision

Source, generation job, job slide and export use independent state machines in `packages/contracts/state-machines.json`. Queued and running generation jobs may enter `cancel_requested`; it is not terminal. The first legal database terminal transaction wins a cancel/publish race. Only succeeded and partially_succeeded generation jobs create an initial presentation revision; partial revisions retain failed slots. Single-page retry addresses stable `slideId`.

Generation source bundles/baseline PPTX and presentation export PPTX have distinct artifact types, immutable manifests, retention policies and idempotency bindings.

## Verification

`pnpm verify:contracts`; G02 race/recovery integration tests; G06/G07 artifact tests.
