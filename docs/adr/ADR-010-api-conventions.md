# ADR-010: HTTP and contract conventions

- Status: accepted
- Date: 2026-08-16
- Owners: engineering
- Related SPEC: 7, 8

## Decision

Use `/v1`, JSON `camelCase`, ULID identifiers, UTC ISO 8601 timestamps, cursor pagination, and RFC 7807 errors extended by `schemaVersion`, `code`, `retryable`, `requestId`, and `fieldErrors`. Writes require `Idempotency-Key`; mutable updates require `If-Match` or an explicit base revision. Asynchronous work returns 202 and `Location`. Unauthorized cross-organization resources return 404.

The logical idempotency key is organization + actor + route + key for HTTP and organization + snapshot + stage + optional stable slide ID for worker stages. Attempt is execution metadata and never changes logical identity.

## Consequences

OpenAPI is the HTTP source of truth and generated TypeScript types are not edited manually.

## Verification

`pnpm verify:contracts`
