# ADR-002: Production identity provider and token exchange

- Status: proposed
- Date: 2026-08-16
- Owners: engineering, security
- Related SPEC: 6.1, 10.1

## Context

G03 needs a production identity provider choice, cookie/JWT boundaries, CSRF controls and an explicit local-only test identity. G00 must not require production credentials.

## Decision

Defer provider selection to G03. The fixed boundary is a FastAPI authorization context containing actor and organization IDs. Any development bypass must be impossible to enable in a production build.

## Verification

G03 production-configuration and cross-organization tests.
