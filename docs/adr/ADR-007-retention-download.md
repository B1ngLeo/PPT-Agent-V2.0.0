# ADR-007: Retention, deletion and download authorization

- Status: accepted
- Date: 2026-08-16
- Owners: product, security, engineering
- Related SPEC: 6.10, 6.11, 10.2, 12.1

## Decision

Adopt the SPEC defaults: seven-day idempotency/events, 24-hour temporary artifacts and a configurable download authorization of 15–900 seconds with a 15-minute default. Buckets have no public policy or ACL. Artifact metadata stores only tenant key, hash, MIME, size, status and retention; it never stores a permanent public URL.

Every re-sign operation resolves an active membership, queries the artifact by `organization_id`, verifies the `published` partition/status/retention and checks object-store size before signing. Issuance creates a database grant and audit record but does not store the signed URL. Logout does not attempt to revoke an already-issued S3 signature; the URL remains a bearer capability only until its short expiry. Artifact revocation/deletion immediately blocks new signatures. G07 finalizes project deletion, object reconciliation and Provider-cache handling.

## Verification

G03 cross-tenant, unsigned/tampered/expired URL, private bucket, object metadata and audit tests; G07 deletion/reconciliation E2E.
