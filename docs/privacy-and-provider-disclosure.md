# P1 privacy and Provider disclosure

## Approved live product data flow

Deterministic Fake Providers remain in automated regression and send no customer data
externally. When `PLANNING_BACKEND=kimi` is enabled, the public API sends the presentation
topic, selected language, opaque source artifact IDs, intent and outline-edit instructions
to a private Provider Gateway. That service sends the planning request through
`https://cf.api.fan/v1` to Kimi `kimi-k3`; the public API and browser never receive the
Kimi credential.

When a user explicitly selects `cover_only` or one `selective` safe-role page and the
tenant count/cost reservation succeeds, the Worker derives a minimal visual description
from the approved page role and summary and sends it through the same gateway to OpenAI
`gpt-image-2`. The prompt prohibits visible text, numbers, logos, watermarks, fake UI and
brand marks. The product sends no source document or source excerpt to the image endpoint
and currently permits at most one generated image per deck. The returned
image is embedded as a referenced media part while slide text and shapes remain editable;
it is also stored as a private tenant artifact for reproducibility. Secrets, signed URLs,
raw prompts and document bodies are excluded from browser bundles, metrics, traces and
repository evidence. ProviderCall records retain a request hash, model, purpose, status,
timing and token/image units rather than raw secret values or response bodies.

Image generation defaults to disabled (`image_scope=none` and the sample environment uses
`IMAGE_GENERATION_ENABLED=false`, `IMAGE_MAX_PER_DECK=0`). Enabling runtime configuration
does not opt a user in: a request must carry the explicit policy and declared path chain,
and only that task receives the image secret. Failed explicit paths cannot switch
providers; unresolved required assets become `Needs-Manual`. Stored audit data contains
the prompt hash and sanitized attempt/provider/license metadata, not raw prompt or response.
Provided images remain tenant-private and record their verified SHA-256, media type,
declared purpose, crop/layout policy and license/source note.

Local release verification enables MinIO SSE-S3 with an explicitly development-only static
KMS key. The current owner-operated local-only scope records production KES/KMS as not
applicable/deferred; the static key remains prohibited for shared, hosted, QA, staging or
production use. Any scope expansion requires an approved KES/KMS deployment first.
Current-object retention is enforced from PostgreSQL and tenant-scoped reconciliation,
while MinIO cleans expired delete markers and stale multipart uploads.

## Retention and user control

Default retention is seven days for idempotency/events, 24 hours for temporary artifacts
and 15 minutes for signed downloads. Published project data remains until user deletion
or the approved product retention policy applies. Deletion revokes access, cancels work,
removes tenant objects asynchronously and leaves an audit result. See
[ADR-007](adr/ADR-007-retention-download.md).

## Approval and remaining deployment control

[ADR-005](adr/ADR-005-provider-policy.md) is accepted. Product, Security and Legal approval
is recorded in [the product decision](evidence/g08-provider-product-decision.md): Kimi
`kimi-k3` for text, OpenAI `gpt-image-2` for images and `cf.api.fan` as the gateway. Synthetic
live smoke has passed. The owner explicitly accepts the currently unverified gateway and
upstream region/retention/training/subprocessor/deletion/contract uncertainty and approves
this disclosure plus unit-based cost accounting. Monetary cost depends on the gateway rate
card and invoice. External, shared, hosted, QA, staging or production use must remain
disabled until Security approves machine evidence for the actual production KES/KMS
deployment; that technical control is not satisfied by this document or the local-only
scope decision.
