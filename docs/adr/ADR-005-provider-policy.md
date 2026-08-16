# ADR-005: Provider development default and production approval

- Status: proposed
- Date: 2026-08-16
- Owners: product, security, legal, engineering
- Related SPEC: 1, 6.4, 10.2, 16

## Context

Development uses Kimi `kimi-k3` for text planning and preconfigures OpenAI `gpt-image-2` for a future image-generation path, while production data region, retention and supplier terms remain undecided. P1 product flows do not invoke the image provider.

## Decision

Use a deterministic Fake Provider for contracts and regression. The server-only Kimi adapter may be smoke-tested when `MOONSHOT_API_KEY` is present. The server-only OpenAI Images adapter may be smoke-tested when `OPENAI_API_KEY` is present, but must not be invoked by the P1 product flow until that scope is separately approved. Production readiness requires approval of both providers' models, regions, retention and supplier terms. Secrets never enter contracts, logs, prompts saved as evidence, container image layers, or browser bundles.

## Verification

Provider request-contract tests, G05 fake regression, optional redacted smoke evidence, and secret-scanning tests.
