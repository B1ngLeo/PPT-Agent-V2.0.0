# G03 identity, tenancy, and private storage design

## Purpose and boundary

G03 replaces the G02 synthetic caller boundary with reusable authenticated user and
organization context. It supplies identity provisioning, membership authorization,
baseline entitlements and usage, tenant-safe artifact metadata, short-lived private
downloads, and audit records. Upload parsing, team administration, payment, quota
settlement, and product UI remain outside this goal.

The implementation is split across:

- `packages/domain`: users, organizations, memberships, entitlements, usage,
  artifacts, download grants, audit data, provisioning, and tenant checks;
- `services/api`: strict OIDC or local-only authentication, tenant dependencies,
  entitlement/usage endpoints, and download authorization;
- `services/worker`: organization identity in every task plus a database tenant
  recheck before work begins;
- `tests/integration/g03`: real PostgreSQL, Redis, and MinIO isolation and migration
  evidence.

## Authentication and tenant context

ADR-002 selects standards-based OIDC without binding the domain to a vendor SDK. In
OIDC mode the API resolves a JWKS signing key and accepts only the configured RSA
algorithms, exact issuer and audience, and required `iss`, `sub`, `aud`, `iat`, and
`exp` claims. It does not fall back to development identity. `AUTH_MODE=local` exists
only for `local` and `test`; application construction fails in staging or production.

The first valid identity transaction takes a PostgreSQL advisory lock over
`issuer + subject`. It creates one user, one personal organization, one owner
membership, and one P1 default entitlement. Eight concurrent first-logins therefore
produce one set of rows. Subsequent requests update non-authoritative profile fields
and resolve an active membership. A requested organization without such a membership
returns the same `404` as an unknown organization.

FastAPI injects one immutable `TenantContext` containing internal user, organization,
membership, role, issuer, and subject. Routes do not accept an organization from a
request body. Job, SSE, entitlement, usage, artifact, and download queries always
include `organization_id`. Celery task payloads carry the organization selected at
enqueue time, and the worker locks and rechecks the job against it before mutation.

## Schema and G02 migration

The G03 Alembic revision adds `users`, `memberships`, `entitlements`, `usage_ledger`,
`artifacts`, `artifact_download_grants`, and `audit_logs`. Organizations gain a unique
slug, personal owner, lock version, and soft-delete timestamp. User HTTP
idempotency records use `actor_kind=user`; the existing service-actor path remains
available for G02 orchestration.

The fixed G02 synthetic organization is converted in place to the local default
user's personal organization. Its primary key is unchanged, so existing snapshots,
jobs, slides, events, outbox rows, reservations, and service actors retain their
foreign keys. The automated migration canary runs
`0001_g02 → head → 0001_g02 → head`, compares all eleven selected job fields at each
stage, verifies the identity seed, and runs Alembic's drift check.

## Private object and download boundary

All objects are addressed as:

```text
tenants/{organizationId}/{quarantine|clean|tmp|published}/{artifactId}
```

Only ULIDs and a fixed partition enter the key; user filenames never do. The MinIO
bucket has no public policy or ACL. Artifact rows store only tenant key, SHA-256,
media type, size, state, and retention timestamps. Before issuing a download the API
locks a tenant-scoped published artifact, validates its partition and key, checks
retention/revocation, and compares the stored size with a real object-store `HEAD`.

The configured signature lifetime is 15–900 seconds, with a 15-minute default.
Issuance persists one grant plus one audit record. The signed URL is returned with
`Cache-Control: no-store` and is never written to artifact, grant, audit, or
idempotency data. An idempotent replay re-signs only for the remainder of the original
expiry and creates no new grant; after that expiry it returns `410` and requires a new
key. Revocation, deletion, tenant mismatch, wrong partition, and missing retention all
fail before signing.

## Audit and log hygiene

Mutating G03/G02 HTTP actions write organization, internal actor, resource,
`request_id`, action, outcome, and a small allowlisted detail set. Keys containing
authorization, token, secret, password, URL, prompt, content, or body are dropped.
Request completion logs contain method, path without query, status, request ID, and
organization ID only; they never inspect headers or bodies. Authentication failures
also return generic details so token validation internals are not disclosed.

## Verification mapping

The [G03 engineering evidence](../evidence/g03-identity-tenancy-storage.md) and
[machine-readable matrix](../evidence/security/g03-tenancy-results.json) cover:

- strict JWT claims and algorithm-downgrade rejection;
- production failure when local authentication is configured;
- concurrent personal-organization provisioning and disabled users;
- same-shape cross-tenant API, organization selection, SSE, worker, artifact, and
  download denial;
- private bucket behavior plus unsigned, path-tampered, and expired real MinIO URLs;
- no credentials, content, complete signature, or stored signed URL;
- lossless G02 migration round trip and schema drift detection.
