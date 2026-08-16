# P0 Gate report

> Decision time: 2026-08-16T11:34:00+08:00
>
> Decision: **passed — G03 may start**

## Scope

This review is the sequential boundary between the two engineering spikes (G01/G02)
and P1 product development (G03 onward). It does not reinterpret a pending item as a
later concern: every required G01 and G02 Gate is passed, and there is no waiver.

## Required Gate status

| Gate                      | Owner       | Status | Primary evidence                                                      |
| ------------------------- | ----------- | ------ | --------------------------------------------------------------------- |
| GATE-G01-UPSTREAM-LICENSE | legal       | passed | [G01 approval record](evidence/g01-approval-record.md)                |
| GATE-G01-PDF-LICENSE      | legal       | passed | [G01 approval record](evidence/g01-approval-record.md)                |
| GATE-G01-POWERPOINT-WPS   | qa          | passed | [G01 QA review](evidence/g01-qa-review.md)                            |
| GATE-G02-RECOVERY         | engineering | passed | [G02 orchestration evidence](evidence/g02-persistent-orchestrator.md) |

The authoritative machine-readable state remains the
[Gate manifest](evidence/gate-manifest.yaml). `pnpm verify:gates --goal G01` reports
3/3 passed and `pnpm verify:gates --goal G02` reports 1/1 passed.

## P0 decision checklist

| PLAN requirement                                                       | Evidence reviewed                                                                                                                                        | Result |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Engine license, attribution, dependency and font posture is deployable | fixed upstream commit/tree, attribution guard, accepted ADR-003/004, CycloneDX SBOM, fixed base image and font manifest                                  | passed |
| Ten golden samples meet SPEC thresholds                                | 10/10 source and render chains, 40 contract-valid artifacts, 30 pages, native editable text/shapes, no dangling media/full-page bitmap fallback          | passed |
| Intake threat harness and Worker isolation hold                        | 13/13 malicious fixtures rejected before parse; fixed image digest, non-root user, no business credentials, attribution guard in build                   | passed |
| Idempotency and Worker-kill recovery hold                              | concurrent idempotency plus actual process exit 86 and PostgreSQL lease reconciliation, ten consecutive rounds                                           | passed |
| Redis restart and SSE reconnect hold                                   | PostgreSQL snapshot/event replay after Redis flush, Last-Event-ID resume/reset/live handoff, ten consecutive rounds                                      | passed |
| OpenAPI/Schema agrees with the spike boundary                          | 26 schemas, 38 endpoints, 166 fixtures, state/event/error/prerequisite verification; G02 response envelope and lifecycle rules reuse the frozen contract | passed |
| No failed item was deferred                                            | zero failed/skipped recovery cases, zero active waiver, zero unresolved G01/G02 defect                                                                   | passed |

## Current-worktree verification

The P0 review reran the relevant checks after G02 was integrated:

- contract materialization and validation: 26 schemas, 38 endpoints, 166 fixtures;
- G01 source security: 13/13 rejected before parse;
- G01 golden regression: 10/10 source, 10/10 render, 40/40 schema artifacts;
- G02 unit verification: 9 API/domain plus 7 Worker tests;
- G02 recovery matrix: 73/73, including all required groups at 10/10;
- API, Worker, and outbox images built from the frozen lock, fixed base digest, and
  non-root `10001:10001` user;
- container E2E: external HTTP `202` creation → outbox → Celery → three ready slides →
  terminal `succeeded`, progress 3/3 and event sequence 10;
- Markdown links, Prettier, Compose configuration, and G01/G02 Gate validators passed.

On this Windows host, a parallel multi-service Compose/Bake command produced a Docker
Desktop gRPC session-header error before entering a Dockerfile. Sequential per-service
builds succeeded with identical Dockerfiles and are the recorded local workaround. It
does not affect image/runtime behavior and did not consume a product waiver.

## Decision and next boundary

P0 is passed. G03 may extend the existing synthetic organization/service actor model
with users and memberships, but its migration must demonstrate that existing G02
snapshot/job/event data survives unchanged. Production authentication, tenant object
storage, entitlements, audit events, and cross-tenant denial remain exclusively owned
by G03; this report does not claim those features already exist.
