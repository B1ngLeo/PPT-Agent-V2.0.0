# Severity and waiver policy

## Severity

- Sev-1 covers cross-organization access, arbitrary code or file execution, unrecoverable data loss, secret disclosure, or total main-flow outage. It cannot be waived.
- Sev-2 covers repeatable supported-flow failure, repair-required PPTX output, clipped or non-editable critical content, or recovery failure. A time-limited waiver requires product, engineering, and security approval.
- Dependency findings with CVSS >= 7.0 or scanner severity High/Critical must be fixed, proven unreachable, or covered by an expiring ADR waiver.

## Waiver fields

Every waiver records an approved ADR, named approver, expiry timestamp, and at least one compensating control. `pnpm verify:gates` rejects expired or incomplete waivers. Automated checks can produce evidence and move human gates to `ready_for_review`; they cannot mark legal, product, security, PowerPoint/WPS, or assistive-technology review as passed.
