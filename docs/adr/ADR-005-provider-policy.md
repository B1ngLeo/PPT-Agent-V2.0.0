# ADR-005: Provider development default and production approval

- Status: proposed
- Date: 2026-08-16
- Owners: product, security, legal, engineering
- Related SPEC: 1, 6.4, 10.2, 16

## Context

Development names DeepSeek `deepseek-v4-pro`, while production data region, retention and supplier terms remain undecided.

## Decision

Use a deterministic Fake Provider for contracts and regression. A server-only DeepSeek adapter may be smoke-tested in G05 when `DEEPSEEK_API_KEY` is present, but production readiness requires approval of model, region, retention and supplier terms. Secrets never enter contracts, logs, prompts saved as evidence, or browser bundles.

## Verification

G05 fake regression, optional redacted smoke evidence, and secret-scanning tests.
