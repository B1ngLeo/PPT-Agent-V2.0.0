# P1 release checklist

Status: **waiting for human Gate**. Automated engineering readiness is complete unless
otherwise marked; this checklist does not authorize a production deployment.

## Engineering and quality

- [x] Contracts, generated types, lint, typecheck, unit and integration suites pass.
- [x] Golden parse/plan/SVG/QA/PPTX suite passes 10/10.
- [x] E2E-001 through E2E-012 have machine evidence.
- [x] Worker kill, Redis restart, SSE reconnect, cancel/publish race and object
      reconciliation each pass ten consecutive iterations.
- [x] Fixed release-image performance baseline passes with 0 errors.
- [x] PostgreSQL plus all private objects restore into isolated targets with matching
      schema/counts/SHA-256.
- [x] G08 migration upgrade/downgrade/re-upgrade and drift check pass in an isolated DB.
- [x] Metrics, traces, structured logs, alert rules, runbook and rollback instructions exist.

## Security, supply chain and compatibility

- [x] Cross-tenant, malicious upload, log redaction, short download and deletion tests pass.
- [x] Private MinIO bucket enforces SSE-S3, has no public policy, applies a safe lifecycle
      rule, and runs bounded stale multipart cleanup; the integration database is isolated.
- [x] Production Node and Python dependency audits report zero known vulnerabilities.
- [x] SBOMs, locks, image digests, upstream license and attribution evidence are current.
- [x] PowerPoint/WPS named visible approval from G01 remains valid; the G08 automated rerun
      passed 10/10 open/editable/export checks in each application and 30/30 visual comparisons.
- [x] No unaccepted Sev-1 or Sev-2 finding and no active waiver.

## Accessibility and privacy decisions

- [x] Axe core-state audit has zero unwaived critical/serious violations.
- [x] 390/768/1440 responsive checks and keyboard-flow evidence pass.
- [ ] A named reviewer completes the Windows accessibility checklist, including exact
      Chromium 200% zoom at all three target widths and the screen-reader main flow, with exact
      browser/assistive-technology versions (NVDA is not installed in the current environment).
- [ ] Product, security and legal approve production Provider model/region/retention/
      supplier terms, production KES/KMS posture and the customer disclosure in
      [the privacy document](privacy-and-provider-disclosure.md).

The final G08 Gate may be changed from `ready_for_review` to `passed` only after the two
unchecked decisions have named approvers and timestamps.
