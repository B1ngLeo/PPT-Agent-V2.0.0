# P1 release Gate report

## Decision

Engineering status: **ready for review**. Release status: **waiting for human Gate**.
All automatable P1 checks have evidence; Windows screen-reader review and the production
Provider/privacy decision are not approved and cannot be replaced by automation.

## Required checks

| Required check | Status | Command or evidence | Owner | Checked at |
|---|---|---|---|---|
| Contracts and generated types | passed | `pnpm verify:contracts` | engineering | 2026-08-16 |
| Root automated verification | passed | `pnpm verify` completed every automated stage; its sole non-zero result was the required G08 human Gate at `ready_for_review` | engineering | 2026-08-16 |
| Web lint/type/build | passed | `pnpm verify:web`; Next.js 16.2.11 | engineering | 2026-08-16 |
| API/domain unit | passed | `pnpm verify:api` | engineering | 2026-08-16 |
| Worker unit/boundary | passed | `pnpm verify:worker` | engineering | 2026-08-16 |
| Real integration | passed | `pnpm verify:integration` | engineering | 2026-08-16 |
| Golden 10/10 | passed | `pnpm verify:golden`; `docs/evidence/g01-golden-results.json` | qa | 2026-08-16 |
| E2E-001–012 | passed | `docs/evidence/g08-e2e-matrix.json`; fresh release-container journey in `docs/evidence/g08-final-browser-e2e.json` | qa | 2026-08-16 |
| Tenant/upload/log security | passed | `pnpm verify:security` | security | 2026-08-16 |
| Dependency risk | passed | `docs/evidence/security/g08-dependency-audit.json` | security | 2026-08-16 |
| Recovery/competition ×10 | passed | `docs/evidence/recovery/g08-recovery-matrix.json` | engineering | 2026-08-16 |
| Object reconciliation | passed | `docs/evidence/g08-reconciliation-junit.xml` | engineering | 2026-08-16 |
| Backup restore | passed | `docs/evidence/operations/g08-backup-restore.json` | engineering | 2026-08-16 |
| Performance | passed | `docs/evidence/performance/g08-api-baseline.json` | engineering | 2026-08-16 |
| Observability/alerts/runbook | passed | `docs/design/g08-observability-release.md`; `infra/observability/alerts.yml`; `docs/runbook.md` | engineering | 2026-08-16 |
| SBOM/locks/digests/attribution | passed | `docs/evidence/g01-supply-chain.json`; regenerated CycloneDX SBOMs | security | 2026-08-16 |
| PowerPoint/WPS visible Gate | passed | G01 named approval plus G08 rerun: 10/10 each and 30/30 visual comparisons | qa | 2026-08-16 |
| Axe/responsive/keyboard | passed | `docs/evidence/accessibility/g08-axe-responsive.json` | qa | 2026-08-16 |
| Windows screen reader | **pending** | NVDA absent; named manual checklist required | qa | — |
| Production Provider/privacy | **pending** | `docs/privacy-and-provider-disclosure.md`; ADR-005 remains proposed | product/security/legal | — |

## Performance and recovery summary

The release API image ran four Uvicorn workers against PostgreSQL 17.6. With 20 virtual
users, 120 seconds warmup and 600 seconds measurement, GET p95 was 72.113 ms and write
p95 was 80.873 ms across 22,131 samples with zero errors. The isolated restore matched
Alembic `ad9d3a5d7be1`, all selected table counts and 64/64 object hashes.

Worker kill, Redis restart, SSE reconnect, cancel/publish race and object divergence each
passed iterations 0–9 without duplicate publication, lost terminal state, half-published
artifacts, double usage or unscoped object removal.

## Severity and deviations

There is no known unaccepted Sev-1 or Sev-2 defect and no dependency advisory. There is
no waiver. The two pending rows are explicit release blockers under PLAN 12.7, not
engineering defects or silent deviations. Production deployment, credentials, DNS and
external Provider traffic remain outside this Goal.

The final release-container browser journey created a fresh eight-slide presentation, edited
and reordered it, regenerated one stable slide, exported exact revision 4 to PPTX, exported
the project snapshot, verified stored bytes and SHA-256, restored history, and rechecked the
390 px layout. One initial request reached the newly recreated API before readiness; after
`/healthz` returned 200, one explicit retry completed the full journey without another error.
