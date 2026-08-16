# G08 PLAN/SPEC completion audit

Audit date: 2026-08-16. This audit treats `PLAN.md` and `SPEC.md` as authoritative and
does not infer completion from a green aggregate command. G09 is explicitly optional P1.1,
requires completed G08 plus approved ADR-009, and has not been started.

## PLAN 12.3 scope

| Requirement                                           | Status                     | Direct evidence                                                                                                                                                                             |
| ----------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full regression and flaky cleanup                     | passed                     | Root `pnpm verify` completed every automated stage; only the required G08 human Gate returned non-zero. `PROGRESS.md` records bounded retries and the six-attempt saturated-load deviation. |
| Tenant, malicious upload, log and dependency security | passed                     | G03/G04/G05 security matrices and `docs/evidence/security/g08-dependency-audit.json`.                                                                                                       |
| SSE/queue/Worker/database/object recovery             | passed                     | `docs/evidence/recovery/g08-recovery-matrix.json`, five scenarios × ten seeds.                                                                                                              |
| Reconciliation, retention, deletion and backup        | passed                     | `docs/evidence/g08-integration-junit.xml`, `docs/evidence/security/g08-object-governance.json`, G07 deletion evidence and `docs/evidence/operations/g08-backup-restore.json`.               |
| Trace/log/metric/alert/audit                          | passed                     | `docs/design/g08-observability-release.md`, `/internal/metrics`, 12 rules under `infra/observability/`, quota/audit durable collectors and `docs/runbook.md`.                               |
| 390/768/1440, axe and keyboard                        | passed                     | `docs/evidence/accessibility/g08-axe-responsive.json`; zero critical/serious violations and no horizontal overflow.                                                                         |
| Exact target Chromium 200% zoom                       | **waiting for human Gate** | Narrow-width behavior is automated, but browser zoom cannot be replaced by CSS/viewport emulation. The named reviewer must execute `docs/evidence/g08-screen-reader-checklist.md`.          |
| Windows screen reader main flow                       | **waiting for human Gate** | NVDA is absent; the signed checklist requires exact OS/browser/AT versions and results.                                                                                                     |
| Fixed performance protocol                            | passed                     | `docs/evidence/performance/g08-api-baseline.json`: required dataset, 20 VUs, 120 s warmup, 600 s measurement, 22,131 samples and zero errors.                                               |
| PowerPoint/WPS compatibility                          | passed                     | G01 named approval plus G08 10/10 per application and 30/30 visual rerun.                                                                                                                   |
| SBOM/digests/locks/attribution                        | passed                     | CycloneDX evidence, lockfiles and `docs/evidence/g01-supply-chain.json`.                                                                                                                    |
| Release report/checklist/runbook/rollback             | passed                     | Required documents exist and local links verify.                                                                                                                                            |

## SPEC 13.3 release Gate

| Gate condition                                 | Status                     | Reason                                                                                                                                                 |
| ---------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Lint/type/unit/contract/integration/golden/E2E | passed                     | Stable root commands execute real checks; no placeholder remains.                                                                                      |
| No unaccepted Sev-1/Sev-2                      | passed                     | Severity record has no open finding or waiver.                                                                                                         |
| PDF license decision                           | passed                     | ADR-003 accepted; pypdf replacement evidence and G01 approval exist.                                                                                   |
| SBOM/locks/digests/attribution                 | passed                     | Current evidence is linked from the release report.                                                                                                    |
| PowerPoint/WPS report                          | passed                     | Named reviewer and exact versions are recorded.                                                                                                        |
| Backup/queue/object/rollback                   | passed                     | Restore, recovery and reconciliation evidence plus rollback document exist.                                                                            |
| Production Provider, retention and disclosure  | **waiting for human Gate** | ADR-005 remains proposed; model/region/supplier retention/terms, production KES/KMS and customer notice require named product/security/legal approval. |
| Monitoring, alerts and incident handling       | passed                     | Metrics, traces, 12 alerts, runbook and degradation procedures exist.                                                                                  |

## SPEC 14 P1 Definition of Done

| Item | Status                     | Evidence/decision                                                                                               |
| ---: | -------------------------- | --------------------------------------------------------------------------------------------------------------- |
|    1 | passed                     | E2E-001–012 matrix is complete.                                                                                 |
|    2 | passed                     | P0 golden and license Gates are passed.                                                                         |
|    3 | passed                     | Fresh browser journeys use PostgreSQL/Redis/MinIO/Celery and real HTTP, with no local timer/history substitute. |
|    4 | passed                     | Refresh recovery, partial handling, stable retry and cancel semantics have integration/browser evidence.        |
|    5 | passed                     | Snapshot, presentation revision and export binding are immutable and directly asserted.                         |
|    6 | passed                     | Tenant/upload/log/download/object-governance checks have direct evidence.                                       |
|    7 | **waiting for human Gate** | Automated WCAG baseline passed; exact Chromium 200% zoom and Windows screen reader remain unsigned.             |
|    8 | **waiting for human Gate** | The release report records all checks, but two required human approval packages remain pending.                 |
|    9 | **waiting for human Gate** | No silent deviation is accepted; ADR-005 cannot become accepted without named product/security/legal approval.  |

## Conclusion

All currently automatable P1 work is implemented and verified. PLAN 12.6 cannot be
claimed because the release report still has required pending human evidence. The correct
state is `waiting_for_human_gate`, not `complete`. The two approval packages are:

1. named Windows QA for exact Chromium 200% zoom and one Windows screen reader;
2. named product/security/legal approval for production Provider/privacy/retention and
   KES/KMS posture.
