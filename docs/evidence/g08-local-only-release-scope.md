# G08 local-only release scope decision

- Decision date: 2026-08-16
- Approver: Xiaobing Li (project owner)
- Approval source: explicit project-task direction on 2026-08-16
- Current distribution scope: local development and owner-operated local use only
- Production KES/KMS status for this scope: not applicable / deferred

The project owner confirmed that the current version is not open to external users. The
deployment-specific production KES/KMS machine-evidence and Security-signature control is
therefore removed as a blocker for the current local-only G08 review. This is a scope
decision, not evidence that production KES/KMS has been deployed or approved.

Compensating controls for the local-only scope are:

- Compose-published PostgreSQL, Redis, MinIO, ClamAV and API ports bind to `127.0.0.1` by
  default; the private Provider Gateway has no host-published port.
- The current version disables image generation and does not inject the image Provider key
  into the Worker.
- Local MinIO SSE-S3 and its development-only static key remain limited to local use.
- Repository, logs, browser bundles and evidence must not contain Provider or storage key
  values.

The production KES/KMS control becomes required again before any of these events:

1. public DNS, public ingress, port forwarding, tunneling or internet-accessible hosting;
2. access by anyone other than the owner on the local machine;
3. shared, team, customer, QA, staging or production data processing;
4. a hosted deployment, production SLA, commercial release or external beta.

Before any trigger, the project must deploy an approved KES/KMS, capture deployment-specific
machine evidence, obtain a named Security signature, update the privacy/release documents,
and rerun the applicable security and release Gates. This decision must not be cited as a
production KES/KMS approval.
