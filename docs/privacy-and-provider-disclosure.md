# P1 privacy and Provider disclosure

## Current release-candidate data flow

The verified P1 release candidate uses the deterministic Fake Provider for planning and
generation regression. In that configuration, no customer topic, source content, prompt
or generated slide content is sent to an external model supplier. PostgreSQL stores
versioned application data and audit records; MinIO stores private tenant-prefixed source
and artifact objects; Redis carries non-authoritative events/tasks.

Kimi `kimi-k3` and OpenAI `gpt-image-2` adapters are server-only and dormant unless their
secrets are supplied. The P1 product flow does not invoke the image Provider. Secrets,
signed URLs, prompts and document bodies are excluded from browser bundles, metrics,
traces and evidence.

## Retention and user control

Default retention is seven days for idempotency/events, 24 hours for temporary artifacts
and 15 minutes for signed downloads. Published project data remains until user deletion
or the approved product retention policy applies. Deletion revokes access, cancels work,
removes tenant objects asynchronously and leaves an audit result. See
[ADR-007](adr/ADR-007-retention-download.md).

## Production decision required

[ADR-005](adr/ADR-005-provider-policy.md) is still proposed. Product, security and legal
must name the production text/image models, processing regions, supplier retention,
training/abuse-review terms, subprocessors, deletion behavior and customer-facing notice.
They must also decide how Provider monetary cost is measured. Until that named approval
is recorded, external Provider secrets must not be configured and the P1 release Gate
remains `ready_for_review`, not `passed`.

