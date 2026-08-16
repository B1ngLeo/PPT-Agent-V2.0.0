# ADR-004: ppt-master version and vendor boundary

- Status: accepted
- Date: 2026-08-16
- Owners: engineering, legal
- Related SPEC: 1, 4.2, 10.3

## Context

The upstream engine must be auditable and isolated from Web/API business code.

## Decision

Pin `ppt-master` tag `v4.7.0` at commit `e8323bfaee249cffe1301ec40fca5875eb544d46`. Vendor the complete upstream `skills/ppt-master` subtree at `vendor/ppt-master` without nested Git metadata or local modifications. Retain its LICENSE, copyright, SPONSORS, official SKILL metadata, third-party notices and attribution guard exactly.

`vendor/ppt-master.vendor.json` records provenance plus a portable canonical tree digest. `scripts/verify_vendor.py` checks the tree, protected files and upstream guard before Worker tests. A versioned `engine-adapter` CLI is the only supported product invocation boundary; other application packages cannot import upstream modules directly.

## Verification

`python scripts/verify_vendor.py`; G01 SBOM, lock, adapter contract and golden tests.

The project owner and OSS compliance owner accepted the distribution and attribution posture on 2026-08-16. Legal sign-off is represented by `GATE-G01-UPSTREAM-LICENSE` and `docs/evidence/g01-approval-record.md`.
