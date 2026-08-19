# P1 release Gate report

## Decision

Engineering status: **passed**. Local-only release status: **passed**. All automatable P1
checks have evidence. Xiaobing Li completed the exact Chromium 200% plus Windows Narrator
review with named versions. Product, Security and Legal Provider approval is complete.
Production KES/KMS is not applicable to the owner-operated local-only scope and becomes
mandatory if that scope expands.

## Required checks

| Required check                  | Status                      | Command or evidence                                                                                                             | Owner                  | Checked at |
| ------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ---------- |
| Contracts and generated types   | passed                      | `pnpm verify:contracts`                                                                                                         | engineering            | 2026-08-16 |
| Root automated verification     | passed                      | All automated stages passed; `pnpm verify:gates --goal G08` passed after named human sign-off                                   | engineering/product    | 2026-08-16 |
| Web lint/type/build             | passed                      | `pnpm verify:web`; Next.js 16.2.11                                                                                              | engineering            | 2026-08-16 |
| API/domain unit                 | passed                      | `pnpm verify:api`                                                                                                               | engineering            | 2026-08-16 |
| Worker unit/boundary            | passed                      | `pnpm verify:worker`                                                                                                            | engineering            | 2026-08-16 |
| Real integration                | passed                      | `pnpm verify:integration`                                                                                                       | engineering            | 2026-08-16 |
| Golden 10/10                    | passed                      | `pnpm verify:golden`; `docs/evidence/g01-golden-results.json`                                                                   | qa                     | 2026-08-16 |
| E2E-001–012                     | passed                      | `docs/evidence/g08-e2e-matrix.json`; fresh release-container journey in `docs/evidence/g08-final-browser-e2e.json`              | qa                     | 2026-08-16 |
| Tenant/upload/log security      | passed                      | `pnpm verify:security`                                                                                                          | security               | 2026-08-16 |
| Dependency risk                 | passed                      | `docs/evidence/security/g08-dependency-audit.json`                                                                              | security               | 2026-08-16 |
| Recovery/competition ×10        | passed                      | `docs/evidence/recovery/g08-recovery-matrix.json`                                                                               | engineering            | 2026-08-16 |
| Object reconciliation           | passed                      | `docs/evidence/g08-integration-junit.xml`                                                                                       | engineering            | 2026-08-16 |
| Object encryption/lifecycle     | passed                      | `docs/evidence/security/g08-object-governance.json`; SSE-S3, private policy, lifecycle and stale multipart runtime settings     | security               | 2026-08-16 |
| Backup restore                  | passed                      | `docs/evidence/operations/g08-backup-restore.json`                                                                              | engineering            | 2026-08-16 |
| Performance                     | passed                      | `docs/evidence/performance/g08-api-baseline.json`                                                                               | engineering            | 2026-08-16 |
| Observability/alerts/runbook    | passed                      | `docs/design/g08-observability-release.md`; `infra/observability/alerts.yml`; `docs/runbook.md`                                 | engineering            | 2026-08-16 |
| SBOM/locks/digests/attribution  | passed                      | `docs/evidence/g01-supply-chain.json`; regenerated CycloneDX SBOMs                                                              | security               | 2026-08-16 |
| PowerPoint/WPS visible Gate     | passed                      | G01 named approval plus G08 rerun: 10/10 each and 30/30 visual comparisons                                                      | qa                     | 2026-08-16 |
| Axe/responsive/keyboard         | passed                      | `docs/evidence/accessibility/g08-axe-responsive.json`                                                                           | qa                     | 2026-08-16 |
| Windows accessibility manual    | passed                      | Xiaobing Li; Windows 11 build 22631; Chrome 151.0.7922.138 at 200%; Windows Narrator 10.0.22621.4974                            | qa                     | 2026-08-16 |
| Production Provider/privacy     | passed                      | Named approval plus ISSUE-002 image policy/path/privacy/quota/audit Gate; one-image PPTX embedding passed with synthetic input  | product/security/legal | 2026-08-19 |
| ISSUE-002 Default content/image | passed                      | [Default Agentic release evidence](evidence/issue002-default-agentic-release.md); 8-page publish/edit/exact-export user journey | engineering/qa         | 2026-08-19 |
| Production KES/KMS              | not applicable (local-only) | Owner-approved local-only scope; mandatory again before external/shared/hosted/QA/staging/production use                        | product                | 2026-08-16 |

## Performance and recovery summary

The release API image ran four Uvicorn workers against PostgreSQL 17.6. With 20 virtual
users, 120 seconds warmup and 600 seconds measurement, GET p95 was 72.113 ms and write
p95 was 80.873 ms across 22,131 samples with zero errors. The isolated restore matched
Alembic `ad9d3a5d7be1`, all selected table counts and 64/64 object hashes.

Worker kill, Redis restart, SSE reconnect, cancel/publish race and object divergence each
passed iterations 0–9 without duplicate publication, lost terminal state, half-published
artifacts, double usage or unscoped object removal.

## Severity and deviations

There is no known unaccepted Sev-1 or Sev-2 defect and no dependency advisory. There is no
waiver and no pending control for the owner-operated local-only scope. Production
deployment, credentials, DNS and external Provider traffic remain outside this Goal. The
KES/KMS row is scope-excluded, not technically passed, and reopens before any scope
expansion.

The product owner selected and, acting for Product/Security/Legal, approved Kimi `kimi-k3`
for text and OpenAI `gpt-image-2` for images.
OpenAI's exact image model is now present in current official documentation; the exact Kimi
model is exposed by the selected `cf.api.fan` gateway through Anthropic Messages rather than
Chat Completions. Synthetic live checks passed structured Kimi JSON and a valid GPT Image 2
PNG without persisting credentials, response content or image bytes; see
`docs/evidence/security/g08-live-provider-smoke.json`. The live product-path check then
validated strict intent and four-slide outline output plus a one-image editable PPTX with
1/1 referenced media; see
`docs/evidence/security/g08-live-product-provider-integration.json`. The owner explicitly
accepted the unverified gateway region/retention/upstream/supplier-term risk. That approval
does not substitute for an actual production KES/KMS deployment. The separate
[local-only scope decision](evidence/g08-local-only-release-scope.md) defers that deployment
control until the product scope expands.

Image generation remains opt-in and the sample/local environment remains disabled. The
ISSUE-002 Release Gate now allows a user-confirmed cover or one selected safe-role image
only when tenant count/cost reservation, frozen non-secret configuration and the scoped
Worker runtime secret all succeed. Environment enablement alone cannot opt a request in.
Failed explicit paths cannot switch provider or silently remove a required asset; they stop
before export as `Needs-Manual` unless the approved Design Spec already declares the exact
Office-native fallback trigger. Generated pictures are independent PPTX media objects, not
full-slide bitmaps, and text/charts/evidence remain native editable content.

The final release-container browser journey created a fresh eight-slide presentation, edited
and reordered it, regenerated one stable slide, exported exact revision 4 to PPTX, exported
the project snapshot, verified stored bytes and SHA-256, restored history, and rechecked the
390 px layout. One initial request reached the newly recreated API before it was ready;
after a bounded API availability probe returned 200, one explicit retry completed the full
journey without another error. The subsequent readiness audit added and verified explicit
`/healthz` and database-backed `/readyz` endpoints on the hardened release image.
