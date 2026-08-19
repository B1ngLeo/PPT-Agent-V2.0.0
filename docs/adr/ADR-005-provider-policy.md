# ADR-005: Provider development default and production approval

- Status: accepted
- Date: 2026-08-16
- Amended: 2026-08-19 (ISSUE-002 image Release Gate)
- Owners: product, security, legal, engineering
- Related SPEC: 1, 6.4, 10.2, 16

## Context

The project owner selected Kimi `kimi-k3` for production text planning, OpenAI
`gpt-image-2` for production image generation, and the third-party gateway
`https://cf.api.fan/v1` on 2026-08-16. OpenAI's current official model documentation lists
the exact image model. The gateway exposes `kimi-k3` through Anthropic Messages protocol
and `gpt-image-2` through the OpenAI Images protocol; redacted live checks for both passed.
The project owner accepted the unverified third-party processing and supplier-term risk in
the Product, Security and Legal roles. Production KES/KMS remains a separate deployment
control and is not covered by this approval; a later local-only scope decision defers it
until any external, shared, hosted, QA, staging or production use.

## Decision

Use a deterministic Fake Provider for contracts and regression. In the live product path,
the public API calls a private, token-authenticated Provider Gateway that alone holds the
Kimi secret; the Worker alone holds the image secret. Record the project owner's
model and gateway selection in `docs/evidence/g08-provider-product-decision.md`. The
server-only Kimi adapter selects OpenAI Chat Completions or Anthropic Messages through
`KIMI_PROTOCOL`; the selected gateway requires `anthropic`. The server-only OpenAI Images
adapter uses the configured OpenAI-compatible base URL.

The default remains `image_scope=none`. An image request requires an explicit user-selected
`cover_only` or `selective` policy, a successful tenant count/cost reservation, frozen
non-secret configuration and an enabled runtime secret. Environment configuration alone
cannot turn on image generation. The current entitlement permits at most one text-free
image per deck and only for approved cover, section, abstract-content or ending roles. The
Worker embeds the image as a referenced, independently replaceable PPTX media part,
publishes the source image and analysis/audit artifacts, and records count plus cost.

`auto` may follow only the path chain frozen at confirmation. Explicit `api` or
`host-native` paths do not switch automated providers. An Office-native substitute may run
only when the approved Design Spec already declares the fallback and trigger; otherwise an
unresolved required resource stops before export as `Needs-Manual`. Image failure never
silently removes the required row or implicitly degrades to a text/shape cover. The owner approved the
customer notice, unit accounting and the identified gateway/upstream uncertainty as an
explicit risk acceptance. Owner-operated local use does not require production KES/KMS;
production readiness still requires machine evidence and Security approval for the deployed
KES/KMS posture. Secrets never enter contracts, logs, prompts saved as evidence, container
image layers, or browser bundles.

## Verification

Provider request-contract tests, private-gateway tests, Fake regression, provided-image
analysis freshness, path-specific failure/Needs-Manual, approved native fallback,
independent-picture embedding/package QA, quota/cost idempotence, redacted live
smoke/product-flow evidence, and secret-scanning tests.
