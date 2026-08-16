# G03 identity, tenancy, and private storage evidence

## Result

G03 is complete. The API now has a reusable authenticated tenant context, every test
identity receives exactly one personal organization and default P1 entitlement, and
API/SSE/worker/object/download access fails closed across organizations. The private
download path was exercised against a real MinIO server; no public bucket policy was
present, unsigned and tampered URLs were rejected, and a real 15-second signature was
rejected after expiry.

The machine-readable matrix contains 8 passed tests, zero failed, and zero skipped.
Its latest evidence SHA-256 is
`D5346370E2659FB7855D57FBEEA7E97D6A0FCD6E7E1C63F7C3E54559A246AF66`.

## Acceptance mapping

| PLAN G03 requirement                               | Engineering evidence                                                                                     | Result |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------ |
| Identity adapter and production-safe configuration | Strict OIDC issuer/audience/time/RSA tests; staging/production local mode construction failure           | passed |
| One personal organization per user                 | Eight-thread first-login advisory-lock test; one user/org/membership/entitlement row                     | passed |
| Reusable authorization context                     | FastAPI dependency supplies internal user, membership, role, and organization to all G02/G03 routes      | passed |
| Cross-tenant API and SSE                           | Alice resource read and event stream return the same `404` to Bob as an unknown ID                       | passed |
| Background tenant validation                       | Wrong-organization worker delivery is rejected before mutation; correct delivery completes               | passed |
| Private object partition                           | ULID-only tenant keys, published-state/retention/key/size validation, no public MinIO policy             | passed |
| Short download authorization                       | One grant/audit, no stored URL, no-store response, unsigned/tampered/expired HTTP checks                 | passed |
| Audit and log redaction                            | actor/resource/request ID asserted; authorization, email, content, and signed URL absent from logs/audit | passed |
| G02 data preservation                              | `0001_g02 → head → 0001_g02 → head`; all 11 job canary fields preserved; no Alembic drift                | passed |

## Executed verification

- `pnpm verify:api`: Ruff plus 15 domain/API tests passed;
- `pnpm verify:security:g03`: 6 strict-auth/key/audit tests passed;
- `pnpm verify:integration:g03`: 8 PostgreSQL/Redis/MinIO cases passed;
- `pnpm verify:container:g03`: API/Worker/outbox images built, all ran as uid
  `10001`, and the two-user job plus private-artifact journey passed;
- G03 migration round trip, identity seed assertion, job fingerprint comparison, and
  Alembic `check`: passed;
- real MinIO private-bucket `HEAD` and presign path: signed fetch returned the exact
  bytes; unsigned, tampered, and expired fetches were denied;
- [machine-readable G03 matrix](security/g03-tenancy-results.json): JUnit-derived
  result, duration, environment, migration canary, and digest.
- [container E2E evidence](security/g03-container-e2e.json): non-root identities,
  services, job status, tenant IDs, private artifact result, and log-redaction result;
  SHA-256 `8FE14F8B1DFFCA70163F6C45678CC9042E259EDC301B1027B2A63A963C683CBE`.

The [G03 design](../design/g03-identity-tenancy-storage.md),
[ADR-002](../adr/ADR-002-identity-provider.md), and
[ADR-007](../adr/ADR-007-retention-download.md) document the reusable boundary and
security decisions.

## Faults found and closed

| Finding                                                                   | Attempts | Resolution                                                                                                                          |
| ------------------------------------------------------------------------- | -------: | ----------------------------------------------------------------------------------------------------------------------------------- |
| MinIO readiness briefly closed the first health connection during startup |        1 | Treat connection reset as a bounded readiness retry; no product request is retried by this code.                                    |
| Migration canary initially used a different synthetic organization ID     |        1 | Bind the canary to G02's fixed organization and service actor constants; full round trip then passed.                               |
| Download idempotency initially persisted the short signed URL             |        1 | Persist only original expiry metadata; replay re-signs for remaining lifetime without another grant and returns `410` after expiry. |

No issue exceeded the five-attempt limit. There are no deferred G03 defects or SPEC
deviations.
