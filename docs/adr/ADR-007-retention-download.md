# ADR-007: Retention, deletion and download authorization

- Status: proposed
- Date: 2026-08-16
- Owners: product, security, engineering
- Related SPEC: 6.10, 6.11, 10.2, 12.1

## Decision

Adopt the SPEC defaults provisionally: seven-day idempotency/events, 24-hour temporary artifacts and 15-minute download authorization. Buckets remain private and every re-sign operation rechecks organization access. G07 must finalize deletion and Provider-cache handling.

## Verification

G03 authorization tests and G07 expiry/deletion E2E.
