# ADR-001: Use ULID for externally visible identifiers

- Status: accepted
- Date: 2026-08-16
- Owners: engineering
- Related SPEC: 7.1, 8.1

## Context

Identifiers must be sortable, opaque, portable across PostgreSQL, JSON Schema, TypeScript and Python, and safe in URLs without a second representation.

## Decision

Use canonical 26-character uppercase ULIDs for API and event identifiers. Database columns use a constrained character representation initially; a later migration may use a native/binary representation without changing the HTTP contract. Array indexes are never resource identity.

## Consequences

Validation uses `^[0-9A-HJKMNP-TV-Z]{26}$`. Creation code must handle same-millisecond monotonic ordering. Stable `outlineSlideId` and `slideId` survive reordering.

## Alternatives considered

UUIDv7 is equally viable but has a longer textual form and less uniform support in the selected baseline libraries.

## Verification

`pnpm verify:contracts`
