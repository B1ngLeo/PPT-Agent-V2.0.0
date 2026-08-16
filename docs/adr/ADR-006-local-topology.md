# ADR-006: Local object store, scanner and service topology

- Status: accepted
- Date: 2026-08-16
- Owners: engineering, security
- Related SPEC: 4.2, 10.1

## Context

G00 needs a repeatable local topology without choosing production cloud services.

## Decision

The root Compose baseline uses PostgreSQL, Redis, private MinIO and ClamAV with exact image tags. PostgreSQL is the only business truth source. MinIO models private buckets; ClamAV failures are fail-closed in G01/G04. Production topology remains a later environment decision.

## Verification

`docker compose config`
