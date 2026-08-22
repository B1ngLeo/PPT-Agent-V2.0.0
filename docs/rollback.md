# P1 rollback procedure

## Preconditions

Declare the incident, freeze new releases, capture current image digests, Alembic head,
alert state and a database/object backup. A rollback never authorizes destructive repair
or cross-tenant access.

## Application-first rollback

1. Stop admission of new generation/export work while allowing safe reads.
2. Set API, Worker and outbox images to the last approved immutable digests.
3. Recreate API first, then outbox and Worker. Confirm non-root users and read-only
   Worker filesystem controls are unchanged.
4. Require `/healthz` and `/readyz` 200, then run authentication, history, job recovery,
   export download, private-bucket encryption/lifecycle and metrics smoke checks.
5. Resume admission only after outbox age and running-job recovery stabilize.

## ISSUE-003 authoring-mode rollback

For an Agent-specific incident that does not require an application image rollback, set
`PRESENTATION_AUTHORING_MODE=deterministic-template` on API admission and recreate the API.
The API freezes this choice only into newly created generation snapshots. Do not edit the
policy in queued/running snapshots, rewrite a workflow profile in PostgreSQL, or replace a
published artifact. Verify the first new fallback job has:

- profile/mode `deterministic-template` and disclosure `template-limited-editable-draft`;
- fallback reason `operator-feature-flag`;
- zero text-Provider and Agent-tool calls;
- visible “模板化受限初稿” manifest/UI/download/filename labeling;
- unchanged artifact IDs and SHA-256 for previously published revisions and exact exports.

Return to `agent-authoring` only through a bounded canary after the failed safety invariant,
same-input quality comparison, and PowerPoint/WPS checks pass. Visual preference decline
alone does not authorize silently replacing an approved revision.

G08 adds `object_reconciliation_runs`; ISSUE-003 adds Agent evidence tables and expands the
workflow profile constraint. Application rollback should normally leave these compatible
tables/constraints in place. The preceding application ignores Agent evidence, which is
safer than deleting audit history.

## Schema rollback

Schema downgrade is exceptional. Drain API/Worker/outbox, take a fresh backup, prove no
G08 reconciliation task is running, and restore-test the backup first. In an isolated
target, validate:

```powershell
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini downgrade -1
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini upgrade head
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini check
```

Do not execute the downgrade against production until engineering and incident command
approve the exact database target and accept loss of G08 reconciliation-run or ISSUE-003
Agent evidence audit rows. Before downgrading the authoring-profile constraint, prove no
`deterministic-template` workflow row exists in the target database.

## Roll-forward and closeout

Prefer a fixed roll-forward after service stability. Re-run the affected E2E, recovery,
security and compatibility checks, reconcile objects, compare usage settlements, and
record the incident timeline plus exact digests in the release report.
